// Fonctions utilitaires JavaScript pour l'interface

// Gestion des messages flash
function showFlashMessage(message, type = 'info') {
    const flashContainer = document.getElementById('flash-messages');
    if (!flashContainer) return;
    
    const flashDiv = document.createElement('div');
    flashDiv.className = `flash-message flash-${type}`;
    flashDiv.textContent = message;
    
    flashContainer.appendChild(flashDiv);
    
    // Auto-suppression après 5 secondes
    setTimeout(() => {
        flashDiv.remove();
    }, 5000);
}

// Gestion de la recherche en temps réel
function setupSearch() {
    const searchInput = document.getElementById('search-input');
    const searchResults = document.getElementById('search-results');
    const loadingSpinner = document.getElementById('loading-spinner');
    
    if (!searchInput || !searchResults) return;
    
    let searchTimeout;
    
    searchInput.addEventListener('input', function() {
        const query = this.value.trim();
        
        // Clear previous timeout
        clearTimeout(searchTimeout);
        
        if (query.length < 2) {
            searchResults.innerHTML = '';
            return;
        }
        
        // Show loading spinner
        if (loadingSpinner) {
            loadingSpinner.style.display = 'block';
        }
        
        // Debounce search
        searchTimeout = setTimeout(() => {
            performSearch(query);
        }, 300);
    });
}

// Effectuer une recherche AJAX
function performSearch(query) {
    const searchResults = document.getElementById('search-results');
    const loadingSpinner = document.getElementById('loading-spinner');
    
    // Use API endpoint that returns JSON search results
    fetch(`/api/search?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            displaySearchResults(data);
        })
        .catch(error => {
            console.error('Erreur de recherche:', error);
            showFlashMessage('Erreur lors de la recherche', 'error');
        })
        .finally(() => {
            if (loadingSpinner) {
                loadingSpinner.style.display = 'none';
            }
        });
}

// Afficher les résultats de recherche
function displaySearchResults(results) {
    const searchResults = document.getElementById('search-results');
    if (!searchResults) return;
    
    if (results.length === 0) {
        searchResults.innerHTML = '<p class="text-center text-muted">Aucun résultat trouvé.</p>';
        return;
    }
    
    const resultsHTML = results.map(result => `
        <div class="result-item fade-in">
            <h3 class="result-title">${result[0]}</h3>
            <p class="result-score">Pertinence: ${(result[1] * 100).toFixed(1)}%</p>
            <p class="result-description">Série trouvée correspondant à votre recherche.</p>
        </div>
    `).join('');
    
    searchResults.innerHTML = resultsHTML;
}

// Gestion des recommandations
function loadRecommendations() {
    const userId = getCurrentUserId();
    if (false && !userId) {
        showFlashMessage('Veuillez vous connecter pour voir vos recommandations', 'info');
        return;
    }
    
    const recommendationsContainer = document.getElementById('recommendations');
    const loadingSpinner = document.getElementById('recommendations-loading');
    
    if (loadingSpinner) {
        loadingSpinner.style.display = 'block';
    }
    
    fetch(`/api/search?exclude_seen=true`)
        .then(response => response.json())
        .then(data => {
            displayRecommendations(data);
        })
        .catch(error => {
            console.error('Erreur de recommandations:', error);
            showFlashMessage('Erreur lors du chargement des recommandations', 'error');
        })
        .finally(() => {
            if (loadingSpinner) {
                loadingSpinner.style.display = 'none';
            }
        });
}

// Afficher les recommandations
function displayRecommendations(recommendations) {
    const recommendationsContainer = document.getElementById('recommendations');
    if (!recommendationsContainer) return;
    
    if (recommendations.length === 0) {
        recommendationsContainer.innerHTML = '<p class="text-center text-muted">Aucune recommandation disponible.</p>';
        return;
    }
    

    const recommendationsHTML = recommendations.map(serie => `
        <div class="result-item fade-in">
            <h3 class="result-title"></h3>
            <div class="star-rating-inline" data-serie="">
                <span class="star" data-rating="1">?</span>
                <span class="star" data-rating="2">?</span>
                <span class="star" data-rating="3">?</span>
                <span class="star" data-rating="4">?</span>
                <span class="star" data-rating="5">?</span>
                <button class="btn btn-small btn-secondary remove-rating" title="Supprimer la note" style="margin-left:8px;">?</button>
            </div>
        </div>
    `).join();
    
    recommendationsContainer.innerHTML = recommendationsHTML;
    // Attach rating handlers
    const items = recommendationsContainer.querySelectorAll('.star-rating-inline');
    items.forEach(item => {
        const serie = item.getAttribute('data-serie');
        item.querySelectorAll('.star').forEach(star => {
            star.style.cursor = 'pointer';
            star.style.color = 'var(--text-muted)';
            star.addEventListener('mouseenter', (e)=>{
                const r = parseInt(star.getAttribute('data-rating'));
                item.querySelectorAll('.star').forEach((s, i)=>{
                    s.style.color = (i < r) ? '#ffd700' : 'var(--text-muted)';
                });
            });
            star.addEventListener('click', ()=>{
                const rating = parseInt(star.getAttribute('data-rating'));
                fetch('/api/rate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ serie_name: serie, rating })
                }).then(r=>r.json()).then(()=>{
                    showFlashMessage('Note enregistr�e', 'success');
                }).catch(()=> showFlashMessage('Erreur lors de la notation', 'error'));
            });
        });
        const removeBtn = item.querySelector('.remove-rating');
        if (removeBtn) {
            removeBtn.addEventListener('click', ()=>{
                // Fallback: send rating 0 to clear
                fetch('/api/rate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ serie_name: serie, rating: 0 })
                }).then(r=>r.json()).then(()=>{
                    item.querySelectorAll('.star').forEach(s => s.style.color = 'var(--text-muted)');
                    showFlashMessage('Note supprim�e', 'success');
                }).catch(()=> showFlashMessage('Erreur lors de la suppression de la note', 'error'));
            });
        }
    });
}

// Gestion des étoiles de notation
function setupStarRating() {
    const starContainers = document.querySelectorAll('.star-rating');
    
    starContainers.forEach(container => {
        const stars = container.querySelectorAll('.star');
        const hiddenInput = container.querySelector('input[type="hidden"]');
        
        stars.forEach((star, index) => {
            star.addEventListener('click', () => {
                setRating(stars, index + 1);
                if (hiddenInput) {
                    hiddenInput.value = index + 1;
                }
            });
            
            star.addEventListener('mouseenter', () => {
                highlightStars(stars, index + 1);
            });
        });
        
        container.addEventListener('mouseleave', () => {
            const currentRating = hiddenInput ? parseInt(hiddenInput.value) : 0;
            highlightStars(stars, currentRating);
        });
    });
}

function setRating(stars, rating) {
    stars.forEach((star, index) => {
        if (index < rating) {
            star.classList.add('active');
        } else {
            star.classList.remove('active');
        }
    });
}

function highlightStars(stars, rating) {
    stars.forEach((star, index) => {
        if (index < rating) {
            star.style.color = '#ffd700';
        } else {
            star.style.color = 'var(--text-muted)';
        }
    });
}

// Obtenir l'ID de l'utilisateur actuel (à adapter selon votre système d'auth)
function getCurrentUserId() {
    // Cette fonction doit être adaptée selon votre système d'authentification
    // Pour l'instant, on retourne null
    return null;
}

// Confirmation de suppression
function confirmDelete(message = 'Êtes-vous sûr de vouloir supprimer cet élément ?') {
    return confirm(message);
}

// Initialisation au chargement de la page
document.addEventListener('DOMContentLoaded', function() {
    setupSearch();
    setupStarRating();
    
    // Auto-hide flash messages
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.opacity = '0';
            setTimeout(() => message.remove(), 300);
        }, 5000);
    });
    
    // Animation d'apparition des éléments
    const animatedElements = document.querySelectorAll('.fade-in');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    });
    
    animatedElements.forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(20px)';
        el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
        observer.observe(el);
    });
});

// Gestion des formulaires
function setupFormValidation() {
    const forms = document.querySelectorAll('form[data-validate]');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!validateForm(this)) {
                e.preventDefault();
            }
        });
    });
}

function validateForm(form) {
    const requiredFields = form.querySelectorAll('[required]');
    let isValid = true;
    
    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            showFieldError(field, 'Ce champ est requis');
            isValid = false;
        } else {
            clearFieldError(field);
        }
    });
    
    // Validation email
    const emailFields = form.querySelectorAll('input[type="email"]');
    emailFields.forEach(field => {
        if (field.value && !isValidEmail(field.value)) {
            showFieldError(field, 'Format d\'email invalide');
            isValid = false;
        }
    });
    
    return isValid;
}

function showFieldError(field, message) {
    clearFieldError(field);
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'field-error';
    errorDiv.textContent = message;
    errorDiv.style.color = 'var(--error-color)';
    errorDiv.style.fontSize = '0.875rem';
    errorDiv.style.marginTop = '0.25rem';
    
    field.parentNode.appendChild(errorDiv);
    field.style.borderColor = 'var(--error-color)';
}

function clearFieldError(field) {
    const existingError = field.parentNode.querySelector('.field-error');
    if (existingError) {
        existingError.remove();
    }
    field.style.borderColor = 'var(--border-color)';
}

function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

// === Enhancements: ratings + recommendations ===
(function(){
  // Cache for user ratings
  let ratingsLoaded = false;
  window.MY_RATINGS = window.MY_RATINGS || null;

  async function fetchMyRatings() {
    if (!window.CURRENT_USER_ID) { window.MY_RATINGS = {}; ratingsLoaded = true; return window.MY_RATINGS; }
    try {
      const r = await fetch('/api/my_ratings');
      if (r.ok) {
        window.MY_RATINGS = await r.json();
      } else {
        window.MY_RATINGS = {};
      }
    } catch (e) {
      window.MY_RATINGS = {};
    }
    ratingsLoaded = true;
    return window.MY_RATINGS;
  }
  window.fetchMyRatings = fetchMyRatings;

  function renderStarWidget(container, serieName, initialScore) {
    container.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'star-rating-inline';
    let score = initialScore || 0;
    const stars = [];
    const setStars = (selected) => {
      stars.forEach((el, idx)=> {
        const n = idx + 1;
        el.className = (n === selected ? 'fas' : 'far') + ' fa-star star';
        el.style.color = (n === selected ? '#ffd700' : 'var(--text-muted)');
      });
    };
    for (let i=1;i<=5;i++){
      const star = document.createElement('i');
      star.className = (i === score ? 'fas' : 'far') + ' fa-star star';
      star.style.cursor = 'pointer';
      star.style.marginRight = '4px';
      star.style.color = (i === score ? '#ffd700' : 'var(--text-muted)');
      star.addEventListener('mouseenter', ()=> {
        stars.forEach((sEl, j)=>{
          const n = j + 1;
          sEl.className = (n === i ? 'fas' : 'far') + ' fa-star star';
          sEl.style.color = (n === i ? '#ffd700' : 'var(--text-muted)');
        });
      });
      star.addEventListener('mouseleave', ()=> setStars(score));
      star.addEventListener('click', async ()=>{
        if (!window.CURRENT_USER_ID) { showFlashMessage('Connectez-vous pour noter', 'info'); return; }
        try {
          const resp = await fetch('/api/rate', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ serie_name: serieName, rating: i })});
          await resp.json();
          score = i; setStars(score);
          if (window.MY_RATINGS) window.MY_RATINGS[serieName] = score;
          removeBtn.style.display = '';
          showFlashMessage('Note enregistrée', 'success');
        } catch(e){ showFlashMessage('Erreur lors de la notation', 'error'); }
      });
      stars.push(star); wrap.appendChild(star);
    }
    const removeBtn = document.createElement('button');
    removeBtn.className = 'btn btn-small btn-secondary remove-rating';
    removeBtn.textContent = '×';
    removeBtn.title = 'Supprimer la note';
    removeBtn.style.marginLeft = '8px';
    removeBtn.style.display = score > 0 ? '' : 'none';
    removeBtn.addEventListener('click', async ()=>{
      if (!window.CURRENT_USER_ID) return;
      try {
        const resp = await fetch('/api/unrate', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ serie_name: serieName })});
        await resp.json();
        score = 0; setStars(score); removeBtn.style.display = 'none';
        if (window.MY_RATINGS) delete window.MY_RATINGS[serieName];
        showFlashMessage('Note supprimée', 'success');
      } catch(e){ showFlashMessage('Erreur lors de la suppression de la note', 'error'); }
    });
    wrap.appendChild(removeBtn);
    container.appendChild(wrap);
    setStars(score);
  }
  window.renderStarWidget = renderStarWidget;

  function attachStarsIn(container) {
    if (!container) return;
    const items = container.querySelectorAll('.result-item');
    items.forEach(item => {
      if (item.querySelector('.star-rating-inline')) return; // already attached
      const titleEl = item.querySelector('.result-title');
      if (!titleEl) return;
      const name = titleEl.textContent.trim();
      const slot = document.createElement('div');
      slot.className = 'stars-slot';
      const descEl = item.querySelector('.result-description');
      const scoreEl = item.querySelector('.result-score');
      if (descEl) {
        item.insertBefore(slot, descEl);
      } else if (scoreEl && scoreEl.nextSibling) {
        item.insertBefore(slot, scoreEl.nextSibling);
      } else {
        item.appendChild(slot);
      }
      const init = (window.MY_RATINGS && window.MY_RATINGS[name]) ? window.MY_RATINGS[name] : 0;
      renderStarWidget(slot, name, init);
    });
  }

  async function initRatingsAndObservers(){
    await fetchMyRatings();
    const searchCont = document.getElementById('search-results');
    const recoCont = document.getElementById('recommendations');
    attachStarsIn(searchCont);
    attachStarsIn(recoCont);
    const cleanDescriptions = (root) => {
      if (!root) return;
      root.querySelectorAll('.result-description').forEach(p => p.remove());
    };
    cleanDescriptions(searchCont);
    const observer = new MutationObserver(() => {
      attachStarsIn(searchCont);
      attachStarsIn(recoCont);
      cleanDescriptions(searchCont);
      enhanceResultsWithMeta('search-results');
      enhanceResultsWithMeta('recommendations');
    });
    if (searchCont) observer.observe(searchCont, { childList: true });
    if (recoCont) observer.observe(recoCont, { childList: true });
  }

  // Override loadRecommendations to use user_id
  window.loadRecommendations = async function(){
    const recommendationsContainer = document.getElementById('recommendations');
    const loadingSpinner = document.getElementById('recommendations-loading');
    if (!window.CURRENT_USER_ID) {
      if (recommendationsContainer) recommendationsContainer.innerHTML = '<p class="text-center text-muted">Connectez-vous pour voir vos recommandations.</p>';
      return;
    }
    if (loadingSpinner) loadingSpinner.style.display = 'block';
    await fetchMyRatings();
    try {
      const resp = await fetch(`/api/search?user_id=${encodeURIComponent(String(window.CURRENT_USER_ID))}`);
      const data = await resp.json();
      // Reuse existing display if present, else simple render
      if (typeof window.displayRecommendations === 'function') {
        window.displayRecommendations(data);
      } else if (recommendationsContainer) {
        recommendationsContainer.innerHTML = data.map(([name, score])=>`<div class="result-item"><h3 class="result-title">${name}</h3><p class="result-score">Score: ${(score*100).toFixed(1)}%</p></div>`).join('');
      }
    } catch(e){
      showFlashMessage('Erreur lors du chargement des recommandations', 'error');
    } finally {
      if (loadingSpinner) loadingSpinner.style.display = 'none';
      attachStarsIn(document.getElementById('recommendations'));
    }
  };

  document.addEventListener('DOMContentLoaded', initRatingsAndObservers);
})();

// Fetch metadata (image, synopsis) and inject into result cards
async function enhanceResultsWithMeta(containerId = 'search-results') {
  const container = document.getElementById(containerId);
  if (!container) return;
  const titles = Array.from(container.querySelectorAll('.result-item .result-title'));
  const names = titles.map(t => t.textContent.trim()).filter(Boolean);
  if (names.length === 0) return;
  try {
    const resp = await fetch(`/api/series_meta?names=${encodeURIComponent(names.join(','))}`);
    if (!resp.ok) return;
    const meta = await resp.json();
    titles.forEach(titleEl => {
      const name = titleEl.textContent.trim();
      const info = meta[name];
      if (!info) return;
      let item = titleEl.closest('.result-item');
      if (!item) return;
      // image
      if (!item.querySelector('.result-media')) {
        const media = document.createElement('div');
        media.className = 'result-media';
        if (info.image_url) {
          const img = document.createElement('img');
          img.className = 'result-image';
          img.src = info.image_url;
          img.alt = name;
          media.appendChild(img);
        } else {
          const ph = document.createElement('div');
          ph.className = 'result-image placeholder';
          media.appendChild(ph);
        }
        item.insertBefore(media, item.firstChild);
      }
      // synopsis
      if (!item.querySelector('.result-description')) {
        const p = document.createElement('p');
        p.className = 'result-description';
        const full = info.synopsis || 'Aucune description disponible.';
        const trimmed = full.length > 400 ? (full.slice(0, 400) + '...') : full;
        p.textContent = trimmed;
        item.appendChild(p);
      }
    });
  } catch (e) { /* ignore */ }
}
