/**
 * AI Settings JavaScript for the Discord Bot Dashboard
 */

// Flag to track if AI settings have been loaded
let aiSettingsLoaded = false;

/**
 * Load AI settings from the API
 */
async function loadAiSettings() {
    try {
        const response = await API.get('/dashboard/api/settings');
        
        if (response) {
            // Populate AI model dropdown
            const modelSelect = document.getElementById('ai-model-select');
            if (response.model) {
                // Find the option with the matching value or create a new one if it doesn't exist
                let option = Array.from(modelSelect.options).find(opt => opt.value === response.model);
                if (!option) {
                    option = new Option(response.model, response.model);
                    modelSelect.add(option);
                }
                modelSelect.value = response.model;
            }

            // Set temperature
            const temperatureSlider = document.getElementById('ai-temperature');
            const temperatureValue = document.getElementById('temperature-value');
            if (response.temperature !== undefined) {
                temperatureSlider.value = response.temperature;
                temperatureValue.textContent = response.temperature;
            }

            // Set max tokens
            const maxTokensInput = document.getElementById('ai-max-tokens');
            if (response.max_tokens !== undefined) {
                maxTokensInput.value = response.max_tokens;
            }

            // Set reasoning settings
            const reasoningCheckbox = document.getElementById('ai-reasoning-enabled');
            const reasoningEffortSelect = document.getElementById('ai-reasoning-effort');
            const reasoningEffortGroup = document.getElementById('reasoning-effort-group');

            if (response.reasoning_enabled !== undefined) {
                reasoningCheckbox.checked = response.reasoning_enabled;
                reasoningEffortGroup.style.display = response.reasoning_enabled ? 'block' : 'none';
            }

            if (response.reasoning_effort) {
                reasoningEffortSelect.value = response.reasoning_effort;
            }

            // Set web search
            const webSearchCheckbox = document.getElementById('ai-web-search-enabled');
            if (response.web_search_enabled !== undefined) {
                webSearchCheckbox.checked = response.web_search_enabled;
            }

            // Set system prompt
            const systemPromptTextarea = document.getElementById('ai-system-prompt');
            if (response.system_message) {
                systemPromptTextarea.value = response.system_message;
            }

            // Set character settings
            const characterInput = document.getElementById('ai-character');
            const characterInfoTextarea = document.getElementById('ai-character-info');
            const characterBreakdownCheckbox = document.getElementById('ai-character-breakdown');

            if (response.character) {
                characterInput.value = response.character;
            }

            if (response.character_info) {
                characterInfoTextarea.value = response.character_info;
            }

            if (response.character_breakdown !== undefined) {
                characterBreakdownCheckbox.checked = response.character_breakdown;
            }

            // Set custom instructions
            const customInstructionsTextarea = document.getElementById('ai-custom-instructions');
            if (response.custom_instructions) {
                customInstructionsTextarea.value = response.custom_instructions;
            }

            aiSettingsLoaded = true;
            Toast.success('AI settings loaded successfully');
        }
    } catch (error) {
        console.error('Error loading AI settings:', error);
        Toast.error('Failed to load AI settings. Please try again.');
    }
}

/**
 * Initialize AI settings functionality
 */
function initAiSettings() {
    // Temperature slider
    const temperatureSlider = document.getElementById('ai-temperature');
    const temperatureValue = document.getElementById('temperature-value');
    
    if (temperatureSlider && temperatureValue) {
        temperatureSlider.addEventListener('input', function() {
            temperatureValue.textContent = this.value;
        });
    }

    // Reasoning checkbox
    const reasoningCheckbox = document.getElementById('ai-reasoning-enabled');
    const reasoningEffortGroup = document.getElementById('reasoning-effort-group');
    
    if (reasoningCheckbox && reasoningEffortGroup) {
        reasoningCheckbox.addEventListener('change', function() {
            reasoningEffortGroup.style.display = this.checked ? 'block' : 'none';
        });
    }

    // Save AI Settings button
    const saveAiSettingsButton = document.getElementById('save-ai-settings-button');
    if (saveAiSettingsButton) {
        saveAiSettingsButton.addEventListener('click', async () => {
            try {
                const settings = {
                    model: document.getElementById('ai-model-select').value,
                    temperature: parseFloat(document.getElementById('ai-temperature').value),
                    max_tokens: parseInt(document.getElementById('ai-max-tokens').value),
                    reasoning_enabled: document.getElementById('ai-reasoning-enabled').checked,
                    reasoning_effort: document.getElementById('ai-reasoning-effort').value,
                    web_search_enabled: document.getElementById('ai-web-search-enabled').checked
                };

                await API.put('/dashboard/api/settings', settings);
                Toast.success('AI settings saved successfully');
            } catch (error) {
                console.error('Error saving AI settings:', error);
                Toast.error('Failed to save AI settings. Please try again.');
            }
        });
    }

    // Reset AI Settings button
    const resetAiSettingsButton = document.getElementById('reset-ai-settings-button');
    if (resetAiSettingsButton) {
        resetAiSettingsButton.addEventListener('click', async () => {
            if (!confirm('Are you sure you want to reset AI settings to defaults?')) return;

            try {
                const defaultSettings = {
                    model: "openai/gpt-3.5-turbo",
                    temperature: 0.7,
                    max_tokens: 1000,
                    reasoning_enabled: false,
                    reasoning_effort: "medium",
                    web_search_enabled: false
                };

                await API.put('/dashboard/api/settings', defaultSettings);

                // Update UI with default values
                document.getElementById('ai-model-select').value = defaultSettings.model;
                document.getElementById('ai-temperature').value = defaultSettings.temperature;
                document.getElementById('temperature-value').textContent = defaultSettings.temperature;
                document.getElementById('ai-max-tokens').value = defaultSettings.max_tokens;
                document.getElementById('ai-reasoning-enabled').checked = defaultSettings.reasoning_enabled;
                document.getElementById('reasoning-effort-group').style.display = defaultSettings.reasoning_enabled ? 'block' : 'none';
                document.getElementById('ai-reasoning-effort').value = defaultSettings.reasoning_effort;
                document.getElementById('ai-web-search-enabled').checked = defaultSettings.web_search_enabled;

                Toast.success('AI settings reset to defaults');
            } catch (error) {
                console.error('Error resetting AI settings:', error);
                Toast.error('Failed to reset AI settings. Please try again.');
            }
        });
    }

    // Save System Prompt button
    const saveSystemPromptButton = document.getElementById('save-system-prompt-button');
    if (saveSystemPromptButton) {
        saveSystemPromptButton.addEventListener('click', async () => {
            try {
                const settings = {
                    system_message: document.getElementById('ai-system-prompt').value
                };

                await API.put('/dashboard/api/settings', settings);
                Toast.success('System prompt saved successfully');
            } catch (error) {
                console.error('Error saving system prompt:', error);
                Toast.error('Failed to save system prompt. Please try again.');
            }
        });
    }

    // Reset System Prompt button
    const resetSystemPromptButton = document.getElementById('reset-system-prompt-button');
    if (resetSystemPromptButton) {
        resetSystemPromptButton.addEventListener('click', async () => {
            if (!confirm('Are you sure you want to reset the system prompt to default?')) return;

            try {
                const settings = {
                    system_message: ""
                };

                await API.put('/dashboard/api/settings', settings);

                // Clear UI
                document.getElementById('ai-system-prompt').value = '';

                Toast.success('System prompt reset to default');
            } catch (error) {
                console.error('Error resetting system prompt:', error);
                Toast.error('Failed to reset system prompt. Please try again.');
            }
        });
    }

    // Save Character Settings button
    const saveCharacterSettingsButton = document.getElementById('save-character-settings-button');
    if (saveCharacterSettingsButton) {
        saveCharacterSettingsButton.addEventListener('click', async () => {
            try {
                const settings = {
                    character: document.getElementById('ai-character').value,
                    character_info: document.getElementById('ai-character-info').value,
                    character_breakdown: document.getElementById('ai-character-breakdown').checked
                };

                await API.put('/dashboard/api/settings', settings);
                Toast.success('Character settings saved successfully');
            } catch (error) {
                console.error('Error saving character settings:', error);
                Toast.error('Failed to save character settings. Please try again.');
            }
        });
    }

    // Clear Character button
    const clearCharacterSettingsButton = document.getElementById('clear-character-settings-button');
    if (clearCharacterSettingsButton) {
        clearCharacterSettingsButton.addEventListener('click', async () => {
            if (!confirm('Are you sure you want to clear character settings?')) return;

            try {
                const settings = {
                    character: "",
                    character_info: "",
                    character_breakdown: false
                };

                await API.put('/dashboard/api/settings', settings);

                // Clear UI
                document.getElementById('ai-character').value = '';
                document.getElementById('ai-character-info').value = '';
                document.getElementById('ai-character-breakdown').checked = false;

                Toast.success('Character settings cleared');
            } catch (error) {
                console.error('Error clearing character settings:', error);
                Toast.error('Failed to clear character settings. Please try again.');
            }
        });
    }

    // Save Custom Instructions button
    const saveCustomInstructionsButton = document.getElementById('save-custom-instructions-button');
    if (saveCustomInstructionsButton) {
        saveCustomInstructionsButton.addEventListener('click', async () => {
            try {
                const settings = {
                    custom_instructions: document.getElementById('ai-custom-instructions').value
                };

                await API.put('/dashboard/api/settings', settings);
                Toast.success('Custom instructions saved successfully');
            } catch (error) {
                console.error('Error saving custom instructions:', error);
                Toast.error('Failed to save custom instructions. Please try again.');
            }
        });
    }

    // Clear Custom Instructions button
    const clearCustomInstructionsButton = document.getElementById('clear-custom-instructions-button');
    if (clearCustomInstructionsButton) {
        clearCustomInstructionsButton.addEventListener('click', async () => {
            if (!confirm('Are you sure you want to clear custom instructions?')) return;

            try {
                const settings = {
                    custom_instructions: ""
                };

                await API.put('/dashboard/api/settings', settings);

                // Clear UI
                document.getElementById('ai-custom-instructions').value = '';

                Toast.success('Custom instructions cleared');
            } catch (error) {
                console.error('Error clearing custom instructions:', error);
                Toast.error('Failed to clear custom instructions. Please try again.');
            }
        });
    }

    // Add event listener for AI settings tab
    const navAiSettings = document.getElementById('nav-ai-settings');
    if (navAiSettings) {
        navAiSettings.addEventListener('click', () => {
            // Load AI settings if not already loaded
            if (!aiSettingsLoaded) {
                loadAiSettings();
            }
        });
    }
}

// Initialize AI settings when the DOM is loaded
document.addEventListener('DOMContentLoaded', initAiSettings);
