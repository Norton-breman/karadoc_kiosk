/**
 * Vérification et application des mises à jour depuis GitHub.
 * Réutilise showConfirmModal()/showAlertModal() définis dans script.js.
 */

document.addEventListener('DOMContentLoaded', function() {
    const statusEl = document.getElementById('update-status');
    const btn = document.getElementById('update-btn');
    const item = document.getElementById('update-item');

    if (!statusEl || !btn) {
        return;
    }

    // Vérifier la disponibilité d'une mise à jour au chargement de la page
    fetch('/update/check')
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                statusEl.textContent = data.error || 'Vérification impossible';
                return;
            }

            if (data.update_available) {
                const n = data.behind;
                statusEl.textContent = `Mise à jour disponible (${n} nouveau${n > 1 ? 'x' : ''} commit${n > 1 ? 's' : ''})`;
                item.classList.add('update-available');
                btn.style.display = '';
            } else {
                statusEl.textContent = `À jour (version ${data.current})`;
            }
        })
        .catch(error => {
            console.error('Erreur:', error);
            statusEl.textContent = 'Vérification impossible (réseau ?)';
        });

    // Lancer la mise à jour au clic
    btn.addEventListener('click', function() {
        showConfirmModal(
            "Installer la mise à jour ? L'application va redémarrer.",
            { confirmText: 'Mettre à jour' }
        ).then(confirmed => {
            if (confirmed) {
                applyUpdate(statusEl, btn);
            }
        });
    });
});

function applyUpdate(statusEl, btn) {
    btn.disabled = true;
    btn.style.opacity = '0.5';
    statusEl.textContent = 'Mise à jour en cours...';

    fetch('/update/apply', {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            let msg = 'Mise à jour appliquée !';
            if (data.deps_updated) {
                msg += ' Les dépendances ont changé : un redémarrage manuel peut être nécessaire.';
            }
            // Laisser au reloader le temps de recharger le code, puis recharger
            // la page pour afficher la nouvelle version.
            showAlertModal(msg).then(() => {
                setTimeout(() => window.location.reload(), 1500);
            });
        } else {
            showAlertModal(data.error || 'Échec de la mise à jour');
            btn.disabled = false;
            btn.style.opacity = '1';
            statusEl.textContent = 'Échec de la mise à jour';
        }
    })
    .catch(error => {
        console.error('Erreur:', error);
        showAlertModal('Erreur lors de la mise à jour');
        btn.disabled = false;
        btn.style.opacity = '1';
        statusEl.textContent = 'Échec de la mise à jour';
    });
}