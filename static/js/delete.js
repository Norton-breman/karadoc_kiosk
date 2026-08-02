/**
 * Gestion de la suppression des fichiers et dossiers
 */

document.addEventListener('DOMContentLoaded', function() {
    // Sélectionner tous les boutons de suppression
    const deleteButtons = document.querySelectorAll('.delete-btn');

    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation(); // Empêcher la propagation vers le lien parent

            const fileId = this.getAttribute('data-file-id');
            const fileName = this.getAttribute('data-file-name');
            const isDir = this.classList.contains('delete-btn-dir');

            // Confirmation de suppression
            const message = isDir
                ? `Êtes-vous sûr de vouloir supprimer le dossier "${fileName}" et tout son contenu ?`
                : `Êtes-vous sûr de vouloir supprimer "${fileName}" ?`;

            showConfirmModal(message).then(confirmed => {
                if (confirmed) {
                    deleteFile(fileId, this);
                }
            });
        });
    });
});

function deleteFile(fileId, buttonElement) {
    // Désactiver le bouton pendant la suppression
    buttonElement.disabled = true;
    buttonElement.style.opacity = '0.5';

    fetch(`/delete_file/${fileId}`, {
        method: 'POST',
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Trouver le conteneur parent et le supprimer avec animation
            // Pour les fichiers avec label, on remonte jusqu'à card-with-label
            // Sinon on prend juste le card-container
            const container = buttonElement.closest('.card-with-label') || buttonElement.closest('.card-container');
            if (container) {
                container.style.transition = 'opacity 0.3s, transform 0.3s';
                container.style.opacity = '0';
                container.style.transform = 'scale(0.8)';

                setTimeout(() => {
                    container.remove();
                }, 300);
            }
        } else {
            showAlertModal(`Erreur lors de la suppression : ${data.error || 'Erreur inconnue'}`);
            buttonElement.disabled = false;
            buttonElement.style.opacity = '1';
        }
    })
    .catch(error => {
        console.error('Erreur:', error);
        showAlertModal('Erreur lors de la suppression du fichier');
        buttonElement.disabled = false;
        buttonElement.style.opacity = '1';
    });
}

/* ---------------------------------------------------------------------------
 * Modal HTML centré (remplace confirm()/alert() natifs de Chromium qui
 * ignorent la taille de l'écran 320x480).
 * ------------------------------------------------------------------------- */

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
                <button type="button" class="app-modal-btn app-modal-confirm">Supprimer</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    return overlay;
}

/**
 * Affiche un modal de confirmation. Retourne une Promise résolue à true
 * (confirmé) ou false (annulé / clic hors du modal).
 */
function showConfirmModal(message) {
    return new Promise(resolve => {
        const overlay = ensureModal();
        const modal = overlay.querySelector('.app-modal');
        const cancelBtn = overlay.querySelector('.app-modal-cancel');
        const confirmBtn = overlay.querySelector('.app-modal-confirm');

        overlay.querySelector('.app-modal-message').textContent = message;
        cancelBtn.style.display = '';
        confirmBtn.textContent = 'Supprimer';

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