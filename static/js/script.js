/**
 * Fonctions partagées (chargées sur toutes les pages via base.html).
 *
 * Modal HTML centré remplaçant confirm()/alert() natifs de Chromium, qui
 * ignorent la taille de l'écran 320x480.
 */

function ensureModal() {
    let overlay = document.getElementById('app-modal-overlay');
    if (overlay) {
        return overlay;
    }

    overlay = document.createElement('div');
    overlay.id = 'app-modal-overlay';
    overlay.className = 'app-modal-overlay';
    overlay.innerHTML = `
        <div class="app-modal" role="dialog" aria-modal="true">
            <p class="app-modal-message"></p>
            <div class="app-modal-actions">
                <button type="button" class="app-modal-btn app-modal-cancel">Annuler</button>
                <button type="button" class="app-modal-btn app-modal-confirm">Confirmer</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    return overlay;
}

/**
 * Affiche un modal de confirmation. Retourne une Promise résolue à true
 * (confirmé) ou false (annulé / clic hors du modal).
 *
 * options : { confirmText, cancelText }
 */
function showConfirmModal(message, options) {
    options = options || {};
    return new Promise(resolve => {
        const overlay = ensureModal();
        const cancelBtn = overlay.querySelector('.app-modal-cancel');
        const confirmBtn = overlay.querySelector('.app-modal-confirm');

        overlay.querySelector('.app-modal-message').textContent = message;
        cancelBtn.style.display = '';
        cancelBtn.textContent = options.cancelText || 'Annuler';
        confirmBtn.textContent = options.confirmText || 'Confirmer';

        function close(result) {
            overlay.classList.remove('visible');
            overlay.removeEventListener('click', onOverlayClick);
            cancelBtn.removeEventListener('click', onCancel);
            confirmBtn.removeEventListener('click', onConfirm);
            resolve(result);
        }

        function onOverlayClick(e) {
            // Fermer uniquement si on clique en dehors du modal
            if (e.target === overlay) {
                close(false);
            }
        }
        function onCancel() { close(false); }
        function onConfirm() { close(true); }

        overlay.addEventListener('click', onOverlayClick);
        cancelBtn.addEventListener('click', onCancel);
        confirmBtn.addEventListener('click', onConfirm);

        overlay.classList.add('visible');
    });
}

/**
 * Affiche un modal d'information (remplace alert()). Un seul bouton "OK".
 * Retourne une Promise résolue à la fermeture.
 */
function showAlertModal(message) {
    return new Promise(resolve => {
        const overlay = ensureModal();
        const cancelBtn = overlay.querySelector('.app-modal-cancel');
        const confirmBtn = overlay.querySelector('.app-modal-confirm');

        overlay.querySelector('.app-modal-message').textContent = message;
        cancelBtn.style.display = 'none';
        confirmBtn.textContent = 'OK';

        function close() {
            overlay.classList.remove('visible');
            overlay.removeEventListener('click', onOverlayClick);
            confirmBtn.removeEventListener('click', onConfirm);
            resolve();
        }

        function onOverlayClick(e) {
            if (e.target === overlay) {
                close();
            }
        }
        function onConfirm() { close(); }

        overlay.addEventListener('click', onOverlayClick);
        confirmBtn.addEventListener('click', onConfirm);

        overlay.classList.add('visible');
    });
}

/**
 * Confirmation générique sur les formulaires : ajouter `data-confirm="message"`
 * (et optionnellement `data-confirm-text="Libellé du bouton"`) sur un <form>
 * pour intercepter son envoi et demander confirmation via le modal HTML.
 */
document.addEventListener('submit', function(e) {
    const form = e.target;
    if (!form.dataset || !form.dataset.confirm || form.dataset.confirmed === 'true') {
        return;
    }

    e.preventDefault();
    showConfirmModal(form.dataset.confirm, { confirmText: form.dataset.confirmText }).then(confirmed => {
        if (confirmed) {
            // submit() programmatique ne redéclenche pas l'événement 'submit'
            form.dataset.confirmed = 'true';
            form.submit();
        }
    });
});