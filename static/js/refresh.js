/**
 * Gestion du rafraîchissement des dossiers
 */

document.addEventListener('DOMContentLoaded', function() {
    // Sélectionner tous les boutons de refresh
    const refreshButtons = document.querySelectorAll('.refresh-btn');

    refreshButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation(); // Empêcher la propagation vers le lien parent

            const folderId = this.getAttribute('data-folder-id');
            const folderName = this.getAttribute('data-folder-name');

            refreshFolder(folderId, folderName, this);
        });
    });
});

function refreshFolder(folderId, folderName, buttonElement) {
    // Désactiver le bouton et ajouter une animation de rotation
    buttonElement.disabled = true;
    buttonElement.classList.add('refreshing');

    // Animation de rotation continue pendant le refresh
    const icon = buttonElement.querySelector('i');
    icon.style.animation = 'spin 1s linear infinite';

    fetch(`/refresh_folder/${folderId}`, {
        method: 'POST',
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        // Arrêter l'animation
        icon.style.animation = '';
        buttonElement.disabled = false;
        buttonElement.classList.remove('refreshing');

        if (data.success) {
            // Si c'est un podcast avec redirection vers la page de sélection
            if (data.redirect && data.url) {
                window.location.href = `/add_podcast?url=${encodeURIComponent(data.url)}`;
            } else {
                // Afficher le message de succès
                const message = data.message || 'Rafraîchissement effectué';
                alert(message);

                // Recharger la page pour afficher les changements
                if (data.added > 0 || data.removed > 0) {
                    window.location.reload();
                }
            }
        } else {
            alert(`Erreur lors du rafraîchissement : ${data.error || 'Erreur inconnue'}`);
        }
    })
    .catch(error => {
        console.error('Erreur:', error);
        icon.style.animation = '';
        buttonElement.disabled = false;
        buttonElement.classList.remove('refreshing');
        alert('Erreur lors du rafraîchissement du dossier');
    });
}

// Ajouter l'animation CSS pour la rotation
const style = document.createElement('style');
style.textContent = `
    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
`;
document.head.appendChild(style);
