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

            if (confirm(message)) {
                deleteFile(fileId, this);
            }
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
            alert(`Erreur lors de la suppression : ${data.error || 'Erreur inconnue'}`);
            buttonElement.disabled = false;
            buttonElement.style.opacity = '1';
        }
    })
    .catch(error => {
        console.error('Erreur:', error);
        alert('Erreur lors de la suppression du fichier');
        buttonElement.disabled = false;
        buttonElement.style.opacity = '1';
    });
}
