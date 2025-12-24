// Gestion du clavier virtuel
(function() {
    let keyboard = null;
    let currentInput = null;

    // Initialisation du clavier au chargement de la page
    document.addEventListener('DOMContentLoaded', function() {
        // Vérifier que Simple-Keyboard est disponible
        if (!window.SimpleKeyboard) {
            return;
        }

        // Créer l'instance du clavier
        try {
            keyboard = new window.SimpleKeyboard.default(".simple-keyboard", {
            onChange: input => onChange(input),
            onKeyPress: button => onKeyPress(button),
            layout: {
                default: [
                    "1 2 3 4 5 6 7 8 9 0",
                    "a z e r t y u i o p",
                    "q s d f g h j k l m",
                    "{shift} w x c v b n {backspace}",
                    "{space} @ . {enter}"
                ],
                shift: [
                    "1 2 3 4 5 6 7 8 9 0",
                    "A Z E R T Y U I O P",
                    "Q S D F G H J K L M",
                    "{shift} W X C V B N {backspace}",
                    "{space} @ . {enter}"
                ]
            },
            display: {
                '{backspace}': '⌫',
                '{enter}': '↵',
                '{shift}': '⇧',
                '{space}': ' '
            },
            theme: "hg-theme-default hg-layout-default",
            buttonTheme: [
                {
                    class: "hg-red",
                    buttons: "{backspace}"
                }
            ]
        });
        } catch (error) {
            return;
        }

        // Utiliser la délégation d'événements pour gérer les inputs
        // Cela fonctionne même pour les inputs ajoutés dynamiquement
        document.addEventListener('focusin', function(e) {
            if (e.target.matches('input[type="text"], input[type="password"], input[type="search"]')) {
                currentInput = e.target;
                showKeyboard();
                // Synchroniser le clavier avec la valeur actuelle
                keyboard.setInput(e.target.value);
            }
        });

        // Cacher le clavier quand on clique en dehors
        document.addEventListener('click', function(e) {
            const keyboardContainer = document.getElementById('keyboard-container');
            const isInput = e.target.matches('input[type="text"], input[type="password"], input[type="search"]');
            const isKeyboard = keyboardContainer && keyboardContainer.contains(e.target);

            if (!isInput && !isKeyboard && currentInput) {
                hideKeyboard();
            }
        });
    });

    function onChange(input) {
        if (currentInput) {
            currentInput.value = input;
            // Déclencher l'événement input pour que les autres scripts puissent réagir
            currentInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }

    function onKeyPress(button) {
        if (button === "{shift}") {
            handleShift();
        } else if (button === "{enter}") {
            handleEnter();
        } else if (button === "{backspace}") {
            // Le backspace est géré automatiquement par Simple-Keyboard
        }
    }

    function handleShift() {
        let currentLayout = keyboard.options.layoutName;
        let shiftToggle = currentLayout === "default" ? "shift" : "default";
        keyboard.setOptions({
            layoutName: shiftToggle
        });
    }

    function handleEnter() {
        if (currentInput) {
            // Simuler la soumission du formulaire si l'input est dans un form
            const form = currentInput.closest('form');
            if (form) {
                form.submit();
            }
            hideKeyboard();
        }
    }

    function showKeyboard() {
        const container = document.getElementById('keyboard-container');
        if (container) {
            container.style.display = 'block';
            // Faire remonter l'input pour qu'il soit visible au-dessus du clavier
            if (currentInput) {
                setTimeout(() => {
                    currentInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }, 100);
            }
        }
    }

    function hideKeyboard() {
        const container = document.getElementById('keyboard-container');
        if (container) {
            container.style.display = 'none';
        }
        currentInput = null;
        // Réinitialiser au layout par défaut
        if (keyboard) {
            keyboard.setOptions({
                layoutName: "default"
            });
        }
    }
})();
