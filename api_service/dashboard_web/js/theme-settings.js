/**
 * Theme Settings JavaScript
 * Handles theme customization for the dashboard
 */

// Flag to track if theme settings have been loaded
let themeSettingsLoaded = false;

// Initialize theme settings when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    initThemeSettings();

    // Add event listener for theme settings tab
    const navThemeSettings = document.getElementById('nav-theme-settings');
    if (navThemeSettings) {
        navThemeSettings.addEventListener('click', () => {
            // Load theme settings if not already loaded
            if (!themeSettingsLoaded) {
                loadThemeSettings();
            }
        });
    }
});

/**
 * Initialize theme settings
 */
function initThemeSettings() {
    // Get theme mode radio buttons
    const themeModeRadios = document.querySelectorAll('input[name="theme_mode"]');

    // Add event listeners to theme mode radio buttons
    themeModeRadios.forEach(radio => {
        radio.addEventListener('change', () => {
            const customThemeSettings = document.getElementById('custom-theme-settings');
            if (radio.value === 'custom') {
                customThemeSettings.style.display = 'block';
            } else {
                customThemeSettings.style.display = 'none';
            }
            updateThemePreview();
        });
    });

    // Add event listeners to color pickers
    const colorInputs = document.querySelectorAll('input[type="color"]');
    colorInputs.forEach(input => {
        // Get the corresponding text input
        const textInput = document.getElementById(`${input.id}-text`);

        // Update text input when color input changes
        input.addEventListener('input', () => {
            textInput.value = input.value;
            updateThemePreview();
        });

        // Update color input when text input changes
        textInput.addEventListener('input', () => {
            // Validate hex color format
            if (/^#[0-9A-F]{6}$/i.test(textInput.value)) {
                input.value = textInput.value;
                updateThemePreview();
            }
        });
    });

    // Add event listener to font family select
    const fontFamilySelect = document.getElementById('font-family');
    fontFamilySelect.addEventListener('change', updateThemePreview);

    // Add event listener to custom CSS textarea
    const customCssTextarea = document.getElementById('custom-css');
    customCssTextarea.addEventListener('input', updateThemePreview);

    // Add event listener to save button
    const saveButton = document.getElementById('save-theme-settings-button');
    saveButton.addEventListener('click', saveThemeSettings);

    // Add event listener to reset button
    const resetButton = document.getElementById('reset-theme-settings-button');
    resetButton.addEventListener('click', resetThemeSettings);
}

/**
 * Load theme settings from API
 */
async function loadThemeSettings() {
    // If theme settings are already loaded, don't fetch them again
    if (themeSettingsLoaded) {
        console.log('Theme settings already loaded, skipping API call');
        return;
    }

    try {
        // Show loading spinner
        const themeSettingsForm = document.getElementById('theme-settings-form');
        themeSettingsForm.innerHTML = '<div class="loading-spinner-container"><div class="loading-spinner"></div></div>';

        // Fetch theme settings from API
        console.log('Fetching theme settings from API');
        const response = await fetch('/dashboard/api/settings');
        if (!response.ok) {
            throw new Error('Failed to load theme settings');
        }

        const data = await response.json();

        // Mark theme settings as loaded
        themeSettingsLoaded = true;

        // Restore the form
        themeSettingsForm.innerHTML = document.getElementById('theme-settings-template').innerHTML;

        // Initialize event listeners again
        initThemeSettings();

        // Set theme settings values
        if (data && data.theme) {
            const theme = data.theme;

            // Set theme mode
            const themeModeRadio = document.querySelector(`input[name="theme_mode"][value="${theme.theme_mode}"]`);
            if (themeModeRadio) {
                themeModeRadio.checked = true;

                // Show/hide custom theme settings
                const customThemeSettings = document.getElementById('custom-theme-settings');
                if (theme.theme_mode === 'custom') {
                    customThemeSettings.style.display = 'block';
                } else {
                    customThemeSettings.style.display = 'none';
                }
            }

            // Set color values
            if (theme.primary_color) {
                document.getElementById('primary-color').value = theme.primary_color;
                document.getElementById('primary-color-text').value = theme.primary_color;
            }

            if (theme.secondary_color) {
                document.getElementById('secondary-color').value = theme.secondary_color;
                document.getElementById('secondary-color-text').value = theme.secondary_color;
            }

            if (theme.accent_color) {
                document.getElementById('accent-color').value = theme.accent_color;
                document.getElementById('accent-color-text').value = theme.accent_color;
            }

            // Set font family
            if (theme.font_family) {
                document.getElementById('font-family').value = theme.font_family;
            }

            // Set custom CSS
            if (theme.custom_css) {
                document.getElementById('custom-css').value = theme.custom_css;
            }

            // Update preview
            updateThemePreview();
        }
    } catch (error) {
        console.error('Error loading theme settings:', error);
        showToast('error', 'Error', 'Failed to load theme settings');
    }
}

/**
 * Update theme preview
 */
function updateThemePreview() {
    const themeMode = document.querySelector('input[name="theme_mode"]:checked').value;
    const primaryColor = document.getElementById('primary-color').value;
    const secondaryColor = document.getElementById('secondary-color').value;
    const accentColor = document.getElementById('accent-color').value;
    const fontFamily = document.getElementById('font-family').value;
    const customCss = document.getElementById('custom-css').value;

    const preview = document.getElementById('theme-preview');

    // Apply theme mode
    if (themeMode === 'dark') {
        preview.classList.add('dark-mode');
        preview.classList.remove('custom-mode');
    } else if (themeMode === 'light') {
        preview.classList.remove('dark-mode');
        preview.classList.remove('custom-mode');
    } else if (themeMode === 'custom') {
        preview.classList.remove('dark-mode');
        preview.classList.add('custom-mode');

        // Apply custom colors
        preview.style.setProperty('--primary-color', primaryColor);
        preview.style.setProperty('--secondary-color', secondaryColor);
        preview.style.setProperty('--accent-color', accentColor);
        preview.style.setProperty('--font-family', fontFamily);

        // Apply custom CSS
        const customStyleElement = document.getElementById('custom-theme-style');
        if (customStyleElement) {
            customStyleElement.textContent = customCss;
        } else {
            const style = document.createElement('style');
            style.id = 'custom-theme-style';
            style.textContent = customCss;
            document.head.appendChild(style);
        }
    }
}

/**
 * Save theme settings
 */
async function saveThemeSettings() {
    try {
        const saveButton = document.getElementById('save-theme-settings-button');
        saveButton.classList.add('btn-loading');

        const themeMode = document.querySelector('input[name="theme_mode"]:checked').value;
        const primaryColor = document.getElementById('primary-color').value;
        const secondaryColor = document.getElementById('secondary-color').value;
        const accentColor = document.getElementById('accent-color').value;
        const fontFamily = document.getElementById('font-family').value;
        const customCss = document.getElementById('custom-css').value;

        // Create theme settings object
        const themeSettings = {
            theme_mode: themeMode,
            primary_color: primaryColor,
            secondary_color: secondaryColor,
            accent_color: accentColor,
            font_family: fontFamily,
            custom_css: customCss
        };

        // Send theme settings to API
        const response = await fetch('/dashboard/api/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                settings: {
                    theme: themeSettings
                }
            })
        });

        if (!response.ok) {
            throw new Error('Failed to save theme settings');
        }

        // Show success message
        const feedbackElement = document.getElementById('theme-settings-feedback');
        feedbackElement.textContent = 'Theme settings saved successfully!';
        feedbackElement.classList.add('text-success');

        // Apply theme to the entire dashboard
        applyThemeToDocument(themeSettings);

        // Show toast notification
        showToast('success', 'Success', 'Theme settings saved successfully!');
    } catch (error) {
        console.error('Error saving theme settings:', error);

        // Show error message
        const feedbackElement = document.getElementById('theme-settings-feedback');
        feedbackElement.textContent = 'Failed to save theme settings. Please try again.';
        feedbackElement.classList.add('text-danger');

        // Show toast notification
        showToast('error', 'Error', 'Failed to save theme settings');
    } finally {
        // Remove loading state from button
        const saveButton = document.getElementById('save-theme-settings-button');
        saveButton.classList.remove('btn-loading');
    }
}

/**
 * Reset theme settings to defaults
 */
function resetThemeSettings() {
    // Set theme mode to light
    document.getElementById('theme-mode-light').checked = true;

    // Hide custom theme settings
    document.getElementById('custom-theme-settings').style.display = 'none';

    // Reset color values
    document.getElementById('primary-color').value = '#5865F2';
    document.getElementById('primary-color-text').value = '#5865F2';
    document.getElementById('secondary-color').value = '#2D3748';
    document.getElementById('secondary-color-text').value = '#2D3748';
    document.getElementById('accent-color').value = '#7289DA';
    document.getElementById('accent-color-text').value = '#7289DA';

    // Reset font family
    document.getElementById('font-family').value = 'Inter, sans-serif';

    // Reset custom CSS
    document.getElementById('custom-css').value = '';

    // Update preview
    updateThemePreview();

    // Show toast notification
    showToast('info', 'Reset', 'Theme settings reset to defaults');
}

/**
 * Apply theme to the entire document
 * @param {Object} theme - Theme settings object
 */
function applyThemeToDocument(theme) {
    // Apply theme mode
    if (theme.theme_mode === 'dark') {
        document.body.classList.add('dark-mode');
        document.body.classList.remove('custom-mode');
    } else if (theme.theme_mode === 'light') {
        document.body.classList.remove('dark-mode');
        document.body.classList.remove('custom-mode');
    } else if (theme.theme_mode === 'custom') {
        document.body.classList.remove('dark-mode');
        document.body.classList.add('custom-mode');

        // Apply custom colors
        document.documentElement.style.setProperty('--primary-color', theme.primary_color);
        document.documentElement.style.setProperty('--secondary-color', theme.secondary_color);
        document.documentElement.style.setProperty('--accent-color', theme.accent_color);
        document.documentElement.style.setProperty('--font-family', theme.font_family);

        // Apply custom CSS
        const customStyleElement = document.getElementById('global-custom-theme-style');
        if (customStyleElement) {
            customStyleElement.textContent = theme.custom_css;
        } else {
            const style = document.createElement('style');
            style.id = 'global-custom-theme-style';
            style.textContent = theme.custom_css;
            document.head.appendChild(style);
        }
    }
}
