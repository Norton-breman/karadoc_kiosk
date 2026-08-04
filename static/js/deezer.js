// Recherche Deezer : interroge le proxy Flask /deezer/search, affiche les
// résultats, et permet de les enregistrer (POST /deezer/save) ou de les jouer
// (navigation vers la page widget).
(function () {
    const queryInput = document.getElementById('deezer-query');
    const searchBtn = document.getElementById('deezer-search-btn');
    const resultsEl = document.getElementById('deezer-results');
    const typeBtns = document.querySelectorAll('.deezer-type-btn');

    if (!queryInput || !resultsEl) {
        return;
    }

    let currentType = 'track';

    // Sélecteur de type (segmenté)
    typeBtns.forEach(btn => {
        btn.addEventListener('click', function () {
            typeBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentType = btn.dataset.type;
            // Relancer la recherche si un terme est déjà saisi
            if (queryInput.value.trim()) {
                runSearch();
            }
        });
    });

    searchBtn.addEventListener('click', runSearch);
    queryInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            runSearch();
        }
    });

    function runSearch() {
        const q = queryInput.value.trim();
        if (!q) {
            return;
        }

        resultsEl.innerHTML = '<p class="deezer-loading">Recherche…</p>';

        const url = '/deezer/search?type=' + encodeURIComponent(currentType) +
                    '&q=' + encodeURIComponent(q);

        fetch(url)
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    resultsEl.innerHTML = '';
                    showAlertModal(data.error);
                    return;
                }
                renderResults(data.results || []);
            })
            .catch(() => {
                resultsEl.innerHTML = '';
                showAlertModal('Erreur lors de la recherche Deezer.');
            });
    }

    function renderResults(results) {
        resultsEl.innerHTML = '';

        if (!results.length) {
            resultsEl.innerHTML = '<p class="deezer-loading">Aucun résultat.</p>';
            return;
        }

        results.forEach(item => {
            const row = document.createElement('div');
            row.className = 'deezer-item';

            // Lien de lecture (cover + infos) → page widget
            const link = document.createElement('a');
            link.className = 'deezer-item-link';
            link.href = '/deezer/play/' + item.type + '/' + item.id +
                        '?title=' + encodeURIComponent(item.title || '');

            const cover = document.createElement('div');
            cover.className = 'deezer-item-cover';
            if (item.cover) {
                cover.style.backgroundImage = "url('" + item.cover + "')";
            } else {
                cover.style.backgroundColor = '#a238ff';
            }

            const info = document.createElement('div');
            info.className = 'deezer-item-info';
            const title = document.createElement('div');
            title.className = 'deezer-item-title';
            title.textContent = item.title || '';
            const subtitle = document.createElement('div');
            subtitle.className = 'deezer-item-subtitle';
            subtitle.textContent = item.subtitle || '';
            info.appendChild(title);
            info.appendChild(subtitle);

            link.appendChild(cover);
            link.appendChild(info);

            // Bouton Enregistrer
            const saveBtn = document.createElement('button');
            saveBtn.type = 'button';
            saveBtn.className = 'deezer-save-btn';
            saveBtn.title = 'Enregistrer';
            saveBtn.innerHTML = '<i class="fas fa-plus"></i>';
            saveBtn.addEventListener('click', function () {
                saveItem(item, saveBtn);
            });

            row.appendChild(link);
            row.appendChild(saveBtn);
            resultsEl.appendChild(row);
        });
    }

    function saveItem(item, btn) {
        btn.disabled = true;

        fetch('/deezer/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                deezer_id: item.id,
                type: item.type,
                title: item.title,
                subtitle: item.subtitle,
                cover: item.cover
            })
        })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    // Marquer visuellement comme enregistré
                    btn.innerHTML = '<i class="fas fa-check"></i>';
                    btn.classList.add('saved');
                    showAlertModal(data.message);
                } else {
                    btn.disabled = false;
                    showAlertModal(data.error || "Impossible d'enregistrer.");
                }
            })
            .catch(() => {
                btn.disabled = false;
                showAlertModal("Impossible d'enregistrer.");
            });
    }
})();