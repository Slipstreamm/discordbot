// This file is kept for backward compatibility
// It will load the new modular JS files

// Load the utility functions
const utilsScript = document.createElement('script');
utilsScript.src = 'js/utils.js';
document.head.appendChild(utilsScript);

// Load the main script
const mainScript = document.createElement('script');
mainScript.src = 'js/main.js';
document.head.appendChild(mainScript);

document.addEventListener('DOMContentLoaded', () => {
    // Auth elements
    const loginButton = document.getElementById('login-button');
    const logoutButton = document.getElementById('logout-button');
    const authSection = document.getElementById('auth-section');
    const dashboardSection = document.getElementById('dashboard-container');
    const usernameSpan = document.getElementById('username');

    // Navigation elements
    const navServerSettings = document.getElementById('nav-server-settings');
    const navAiSettings = document.getElementById('nav-ai-settings');
    const navConversations = document.getElementById('nav-conversations');

    // Section elements
    const serverSettingsSection = document.getElementById('server-settings-section');
    const aiSettingsSection = document.getElementById('ai-settings-section');
    const conversationsSection = document.getElementById('conversations-section');

    // Server settings elements
    const guildSelect = document.getElementById('guild-select');
    const settingsForm = document.getElementById('settings-form');

    // --- API Base URL (Adjust if needed) ---
    // Assuming the API runs on the same host/port for simplicity,
    // otherwise, use the full URL like 'http://localhost:8000'
    // IMPORTANT: This will need to be updated to the new merged endpoint prefix, e.g., /dashboard/api
    const API_BASE_URL = '/dashboard/api'; // Tentative new prefix

    // --- Helper Functions ---
    async function fetchAPI(endpoint, options = {}) {
        // Add authentication headers if needed (e.g., from cookies or localStorage)
        // For now, assuming cookies handle session management automatically
        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
            if (response.status === 401) { // Unauthorized
                showLogin();
                throw new Error('Unauthorized');
            }
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
                throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
            }
            if (response.status === 204) { // No Content
                return null;
            }
            return await response.json();
        } catch (error) {
            console.error('API Fetch Error:', error);
            // Display error to user?
            throw error; // Re-throw for specific handlers
        }
    }

    function showLogin() {
        authSection.style.display = 'block';
        dashboardSection.style.display = 'none';
        settingsForm.style.display = 'none';
        guildSelect.value = ''; // Reset guild selection
    }

    function showDashboard(userData) {
        authSection.style.display = 'none';
        dashboardSection.style.display = 'block';
        usernameSpan.textContent = userData.username;

        // Show server settings section by default
        showSection('server-settings');

        // Load guilds for server settings
        loadGuilds();
    }

    function displayFeedback(elementId, message, isError = false) {
        const feedbackElement = document.getElementById(elementId);
        if (feedbackElement) {
            feedbackElement.textContent = message;
            feedbackElement.className = isError ? 'error' : '';
            // Clear feedback after a few seconds
            setTimeout(() => {
                feedbackElement.textContent = '';
                feedbackElement.className = '';
            }, 5000);
        }
    }

    // --- Authentication ---
    async function checkLoginStatus() {
        try {
            // Use the new endpoint path
            const userData = await fetchAPI('/user/me');
            if (userData) {
                showDashboard(userData);
            } else {
                showLogin();
            }
        } catch (error) {
            // If fetching /user/me fails (e.g., 401), show login
            showLogin();
        }
    }

    loginButton.addEventListener('click', () => {
        // Redirect to backend login endpoint which will redirect to Discord
        // Use the new endpoint path
        window.location.href = `${API_BASE_URL}/auth/login`;
    });

    logoutButton.addEventListener('click', async () => {
        try {
             // Use the new endpoint path
            await fetchAPI('/auth/logout', { method: 'POST' });
            showLogin();
        } catch (error) {
            alert('Logout failed. Please try again.');
        }
    });

    // --- Guild Loading and Settings ---
    async function loadGuilds() {
        try {
             // Use the new endpoint path
            const guilds = await fetchAPI('/user/guilds');
            guildSelect.innerHTML = '<option value="">--Please choose a server--</option>'; // Reset
            guilds.forEach(guild => {
                // Only add guilds where the user is an administrator (assuming API filters this)
                // Or filter here based on permissions if API doesn't
                // const isAdmin = (parseInt(guild.permissions) & 0x8) === 0x8; // Check ADMINISTRATOR bit
                // if (isAdmin) {
                    const option = document.createElement('option');
                    option.value = guild.id;
                    option.textContent = guild.name;
                    guildSelect.appendChild(option);
                // }
            });
        } catch (error) {
            displayFeedback('guild-select-feedback', `Error loading guilds: ${error.message}`, true); // Add a feedback element if needed
        }
    }

    guildSelect.addEventListener('change', async (event) => {
        const guildId = event.target.value;
        if (guildId) {
            await loadSettings(guildId);
            settingsForm.style.display = 'block';
        } else {
            settingsForm.style.display = 'none';
        }
    });

    async function loadSettings(guildId) {
        console.log(`Loading settings for guild ${guildId}`);
        // Clear previous settings
        document.getElementById('prefix-input').value = '';
        document.getElementById('welcome-channel').value = '';
        document.getElementById('welcome-message').value = '';
        document.getElementById('goodbye-channel').value = '';
        document.getElementById('goodbye-message').value = '';
        document.getElementById('cogs-list').innerHTML = '';
        document.getElementById('current-perms').innerHTML = '';

        // Clear channel dropdowns
        document.getElementById('welcome-channel-select').innerHTML = '<option value="">-- Select Channel --</option>';
        document.getElementById('goodbye-channel-select').innerHTML = '<option value="">-- Select Channel --</option>';

        try {
            // Load guild channels for dropdowns
            await loadGuildChannels(guildId);

            // Use the new endpoint path
            const settings = await fetchAPI(`/guilds/${guildId}/settings`);
            console.log("Received settings:", settings);

            // Populate Prefix
            document.getElementById('prefix-input').value = settings.prefix || '';

            // Populate Welcome/Goodbye Channel IDs
            document.getElementById('welcome-channel').value = settings.welcome_channel_id || '';
            document.getElementById('welcome-message').value = settings.welcome_message || '';
            document.getElementById('goodbye-channel').value = settings.goodbye_channel_id || '';
            document.getElementById('goodbye-message').value = settings.goodbye_message || '';

            // Set the channel dropdowns to match the channel IDs
            if (settings.welcome_channel_id) {
                const welcomeChannelSelect = document.getElementById('welcome-channel-select');
                if (welcomeChannelSelect.querySelector(`option[value="${settings.welcome_channel_id}"]`)) {
                    welcomeChannelSelect.value = settings.welcome_channel_id;
                }
            }

            if (settings.goodbye_channel_id) {
                const goodbyeChannelSelect = document.getElementById('goodbye-channel-select');
                if (goodbyeChannelSelect.querySelector(`option[value="${settings.goodbye_channel_id}"]`)) {
                    goodbyeChannelSelect.value = settings.goodbye_channel_id;
                }
            }

            // Populate Cogs
            // TODO: Need a way to get the *full* list of available cogs from the bot/API
            // For now, just display the ones returned by the settings endpoint
            populateCogsList(settings.enabled_cogs || {});

            // Populate Command Permissions
            // TODO: Fetch roles and commands for dropdowns
            await loadCommandPermissions(guildId);

            // Load guild roles for the role dropdown
            await loadGuildRoles(guildId);

            // Load commands for the command dropdown
            await loadCommands(guildId);

        } catch (error) {
             displayFeedback('prefix-feedback', `Error loading settings: ${error.message}`, true);
        }
    }

    async function loadGuildChannels(guildId) {
        try {
            // Fetch channels from the API
            const channels = await fetchAPI(`/guilds/${guildId}/channels`);

            // Get the channel select dropdowns
            const welcomeChannelSelect = document.getElementById('welcome-channel-select');
            const goodbyeChannelSelect = document.getElementById('goodbye-channel-select');

            // Clear existing options except the default
            welcomeChannelSelect.innerHTML = '<option value="">-- Select Channel --</option>';
            goodbyeChannelSelect.innerHTML = '<option value="">-- Select Channel --</option>';

            // Add text channels to the dropdowns
            channels.filter(channel => channel.type === 0).forEach(channel => {
                const option = document.createElement('option');
                option.value = channel.id;
                option.textContent = `#${channel.name}`;

                // Add to both dropdowns
                welcomeChannelSelect.appendChild(option.cloneNode(true));
                goodbyeChannelSelect.appendChild(option);
            });

            // Add event listeners to sync the dropdowns with the text inputs
            welcomeChannelSelect.addEventListener('change', function() {
                document.getElementById('welcome-channel').value = this.value;
            });

            goodbyeChannelSelect.addEventListener('change', function() {
                document.getElementById('goodbye-channel').value = this.value;
            });

        } catch (error) {
            console.error('Error loading guild channels:', error);
        }
    }

    async function loadGuildRoles(guildId) {
        try {
            // Fetch roles from the API
            const roles = await fetchAPI(`/guilds/${guildId}/roles`);

            // Get the role select dropdown
            const roleSelect = document.getElementById('role-select');

            // Clear existing options except the default
            roleSelect.innerHTML = '<option value="">-- Select Role --</option>';

            // Add roles to the dropdown
            roles.forEach(role => {
                // Skip @everyone role
                if (role.name === '@everyone') return;

                const option = document.createElement('option');
                option.value = role.id;
                option.textContent = role.name;
                roleSelect.appendChild(option);
            });

        } catch (error) {
            console.error('Error loading guild roles:', error);
        }
    }

    async function loadCommands(guildId) {
        try {
            // Fetch commands from the API
            const commands = await fetchAPI(`/guilds/${guildId}/commands`);

            // Get the command select dropdown
            const commandSelect = document.getElementById('command-select');

            // Clear existing options except the default
            commandSelect.innerHTML = '<option value="">-- Select Command --</option>';

            // Add commands to the dropdown
            commands.forEach(command => {
                const option = document.createElement('option');
                option.value = command.name;
                option.textContent = command.name;
                commandSelect.appendChild(option);
            });

        } catch (error) {
            console.error('Error loading commands:', error);
        }
    }

     function populateCogsList(cogsStatus) {
        // This function now only displays cogs whose status is stored in the DB
        // and returned by the API. It doesn't know about *all* possible cogs.
        const cogsListDiv = document.getElementById('cogs-list');
        cogsListDiv.innerHTML = ''; // Clear previous
        // Assuming CORE_COGS is available globally or passed somehow
        // TODO: Get this list from the API or config
        const CORE_COGS = ['SettingsCog', 'HelpCog']; // Example - needs to match backend

        // TODO: Fetch the *full* list of cogs from the bot/API to display all options
        // For now, only showing cogs already in the settings response
        Object.entries(cogsStatus).sort().forEach(([cogName, isEnabled]) => {
            const div = document.createElement('div');
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `cog-${cogName}`;
            checkbox.name = cogName;
            checkbox.checked = isEnabled;
            checkbox.disabled = CORE_COGS.includes(cogName); // Disable core cogs

            const label = document.createElement('label');
            label.htmlFor = `cog-${cogName}`;
            label.textContent = cogName + (CORE_COGS.includes(cogName) ? ' (Core)' : '');

            div.appendChild(checkbox);
            div.appendChild(label);
            cogsListDiv.appendChild(div);
        });
    }

    async function loadCommandPermissions(guildId) {
        const permsDiv = document.getElementById('current-perms');
        permsDiv.innerHTML = 'Loading permissions...';
        try {
            // Use the new endpoint path
            const permData = await fetchAPI(`/guilds/${guildId}/permissions`);
            permsDiv.innerHTML = ''; // Clear loading message
            if (Object.keys(permData.permissions).length === 0) {
                permsDiv.innerHTML = '<i>No specific command permissions set. All roles can use all enabled commands (unless restricted by default).</i>';
                return;
            }

            // TODO: Fetch role names from Discord API or bot API to display names instead of IDs
            for (const [commandName, roleIds] of Object.entries(permData.permissions).sort()) {
                const rolesStr = roleIds.map(id => `Role ID: ${id}`).join(', '); // Placeholder until role names are fetched
                const div = document.createElement('div');
                div.innerHTML = `Command <span>${commandName}</span> allowed for: ${rolesStr}`;
                permsDiv.appendChild(div);
            }
        } catch (error) {
            permsDiv.innerHTML = `<i class="error">Error loading permissions: ${error.message}</i>`;
        }
    }


    // --- Save Settings Event Listeners ---

    document.getElementById('save-prefix-button').addEventListener('click', async () => {
        const guildId = guildSelect.value;
        const prefix = document.getElementById('prefix-input').value;
        if (!guildId) return;

        try {
             // Use the new endpoint path
            await fetchAPI(`/guilds/${guildId}/settings`, {
                method: 'PATCH', // Use PATCH for partial updates
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prefix: prefix })
            });
            displayFeedback('prefix-feedback', 'Prefix saved successfully!');
        } catch (error) {
            displayFeedback('prefix-feedback', `Error saving prefix: ${error.message}`, true);
        }
    });

     document.getElementById('save-welcome-button').addEventListener('click', async () => {
        const guildId = guildSelect.value;
        const channelIdInput = document.getElementById('welcome-channel').value;
        const message = document.getElementById('welcome-message').value;
        if (!guildId) return;

        // Basic validation for channel ID (numeric)
        const channelId = channelIdInput && /^\d+$/.test(channelIdInput) ? channelIdInput : null;

        try {
             // Use the new endpoint path
            await fetchAPI(`/guilds/${guildId}/settings`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    welcome_channel_id: channelId, // Send numeric ID or null
                    welcome_message: message
                 })
            });
            displayFeedback('welcome-feedback', 'Welcome settings saved!');
        } catch (error) {
            displayFeedback('welcome-feedback', `Error saving welcome settings: ${error.message}`, true);
        }
    });

    document.getElementById('disable-welcome-button').addEventListener('click', async () => {
        const guildId = guildSelect.value;
        if (!guildId) return;
        if (!confirm('Are you sure you want to disable welcome messages?')) return;

        try {
             // Use the new endpoint path
            await fetchAPI(`/guilds/${guildId}/settings`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    welcome_channel_id: null,
                    welcome_message: null // Also clear message template maybe? Or just channel? Let's clear both.
                 })
            });
            // Clear the form fields visually
            document.getElementById('welcome-channel').value = '';
            document.getElementById('welcome-message').value = '';
            displayFeedback('welcome-feedback', 'Welcome messages disabled.');
        } catch (error) {
            displayFeedback('welcome-feedback', `Error disabling welcome messages: ${error.message}`, true);
        }
    });

     document.getElementById('save-goodbye-button').addEventListener('click', async () => {
        const guildId = guildSelect.value;
        const channelIdInput = document.getElementById('goodbye-channel').value;
        const message = document.getElementById('goodbye-message').value;
        if (!guildId) return;

        const channelId = channelIdInput && /^\d+$/.test(channelIdInput) ? channelIdInput : null;

        try {
             // Use the new endpoint path
            await fetchAPI(`/guilds/${guildId}/settings`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    goodbye_channel_id: channelId,
                    goodbye_message: message
                 })
            });
            displayFeedback('goodbye-feedback', 'Goodbye settings saved!');
        } catch (error) {
            displayFeedback('goodbye-feedback', `Error saving goodbye settings: ${error.message}`, true);
        }
    });

     document.getElementById('disable-goodbye-button').addEventListener('click', async () => {
        const guildId = guildSelect.value;
        if (!guildId) return;
         if (!confirm('Are you sure you want to disable goodbye messages?')) return;

        try {
             // Use the new endpoint path
            await fetchAPI(`/guilds/${guildId}/settings`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    goodbye_channel_id: null,
                    goodbye_message: null
                 })
            });
             document.getElementById('goodbye-channel').value = '';
             document.getElementById('goodbye-message').value = '';
            displayFeedback('goodbye-feedback', 'Goodbye messages disabled.');
        } catch (error) {
            displayFeedback('goodbye-feedback', `Error disabling goodbye messages: ${error.message}`, true);
        }
    });

    document.getElementById('save-cogs-button').addEventListener('click', async () => {
        const guildId = guildSelect.value;
        if (!guildId) return;

        const cogsPayload = {};
        const checkboxes = document.querySelectorAll('#cogs-list input[type="checkbox"]');
        checkboxes.forEach(cb => {
            if (!cb.disabled) { // Don't send status for disabled (core) cogs
                 cogsPayload[cb.name] = cb.checked;
            }
        });

        try {
             // Use the new endpoint path
            await fetchAPI(`/guilds/${guildId}/settings`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cogs: cogsPayload })
            });
            displayFeedback('cogs-feedback', 'Module settings saved!');
        } catch (error) {
            displayFeedback('cogs-feedback', `Error saving module settings: ${error.message}`, true);
        }
    });

    // --- Command Permissions Event Listeners ---
    document.getElementById('add-perm-button').addEventListener('click', async () => {
        const guildId = guildSelect.value;
        const commandName = document.getElementById('command-select').value;
        const roleId = document.getElementById('role-select').value;
        if (!guildId || !commandName || !roleId) {
            displayFeedback('perms-feedback', 'Please select a command and a role.', true);
            return;
        }

        try {
            // Use the new endpoint path
            await fetchAPI(`/guilds/${guildId}/permissions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command_name: commandName, role_id: roleId })
            });
            displayFeedback('perms-feedback', `Permission added for ${commandName}.`);
            await loadCommandPermissions(guildId); // Refresh list
        } catch (error) {
            displayFeedback('perms-feedback', `Error adding permission: ${error.message}`, true);
        }
    });

    document.getElementById('remove-perm-button').addEventListener('click', async () => {
        const guildId = guildSelect.value;
        const commandName = document.getElementById('command-select').value;
        const roleId = document.getElementById('role-select').value;
         if (!guildId || !commandName || !roleId) {
            displayFeedback('perms-feedback', 'Please select a command and a role to remove.', true);
            return;
        }
         if (!confirm(`Are you sure you want to remove permission for role ID ${roleId} from command ${commandName}?`)) return;

        try {
             // Use the new endpoint path
            await fetchAPI(`/guilds/${guildId}/permissions`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command_name: commandName, role_id: roleId })
            });
            displayFeedback('perms-feedback', `Permission removed for ${commandName}.`);
            await loadCommandPermissions(guildId); // Refresh list
        } catch (error) {
            displayFeedback('perms-feedback', `Error removing permission: ${error.message}`, true);
        }
    });


    // --- Navigation Functions ---
    function showSection(sectionId) {
        // Hide all sections
        serverSettingsSection.style.display = 'none';
        aiSettingsSection.style.display = 'none';
        conversationsSection.style.display = 'none';

        // Remove active class from all nav buttons
        navServerSettings.classList.remove('active');
        navAiSettings.classList.remove('active');
        navConversations.classList.remove('active');

        // Show the selected section and activate the corresponding nav button
        switch(sectionId) {
            case 'server-settings':
                serverSettingsSection.style.display = 'block';
                navServerSettings.classList.add('active');
                break;
            case 'ai-settings':
                aiSettingsSection.style.display = 'block';
                navAiSettings.classList.add('active');
                // Load AI settings if not already loaded
                if (!aiSettingsLoaded) {
                    loadAiSettings();
                }
                break;
            case 'conversations':
                conversationsSection.style.display = 'block';
                navConversations.classList.add('active');
                // Load conversations if not already loaded
                if (!conversationsLoaded) {
                    loadConversations();
                }
                break;
            default:
                serverSettingsSection.style.display = 'block';
                navServerSettings.classList.add('active');
        }
    }

    // --- Navigation Event Listeners ---
    navServerSettings.addEventListener('click', () => showSection('server-settings'));
    navAiSettings.addEventListener('click', () => showSection('ai-settings'));
    navConversations.addEventListener('click', () => showSection('conversations'));

    // --- AI Settings Functions ---
    async function loadAiSettings() {
        try {
            const response = await fetchAPI('/settings');
            const settings = response.settings || response.user_settings;

            if (settings) {
                // Populate AI model dropdown
                const modelSelect = document.getElementById('ai-model-select');
                if (settings.model_id) {
                    // Find the option with the matching value or create a new one if it doesn't exist
                    let option = Array.from(modelSelect.options).find(opt => opt.value === settings.model_id);
                    if (!option) {
                        option = new Option(settings.model_id, settings.model_id);
                        modelSelect.add(option);
                    }
                    modelSelect.value = settings.model_id;
                }

                // Set temperature
                const temperatureSlider = document.getElementById('ai-temperature');
                const temperatureValue = document.getElementById('temperature-value');
                if (settings.temperature !== undefined) {
                    temperatureSlider.value = settings.temperature;
                    temperatureValue.textContent = settings.temperature;
                }

                // Set max tokens
                const maxTokensInput = document.getElementById('ai-max-tokens');
                if (settings.max_tokens !== undefined) {
                    maxTokensInput.value = settings.max_tokens;
                }

                // Set reasoning settings
                const reasoningCheckbox = document.getElementById('ai-reasoning-enabled');
                const reasoningEffortSelect = document.getElementById('ai-reasoning-effort');
                const reasoningEffortGroup = document.getElementById('reasoning-effort-group');

                if (settings.reasoning_enabled !== undefined) {
                    reasoningCheckbox.checked = settings.reasoning_enabled;
                    reasoningEffortGroup.style.display = settings.reasoning_enabled ? 'block' : 'none';
                }

                if (settings.reasoning_effort) {
                    reasoningEffortSelect.value = settings.reasoning_effort;
                }

                // Set web search
                const webSearchCheckbox = document.getElementById('ai-web-search-enabled');
                if (settings.web_search_enabled !== undefined) {
                    webSearchCheckbox.checked = settings.web_search_enabled;
                }

                // Set system prompt
                const systemPromptTextarea = document.getElementById('ai-system-prompt');
                if (settings.system_message) {
                    systemPromptTextarea.value = settings.system_message;
                }

                // Set character settings
                const characterInput = document.getElementById('ai-character');
                const characterInfoTextarea = document.getElementById('ai-character-info');
                const characterBreakdownCheckbox = document.getElementById('ai-character-breakdown');

                if (settings.character) {
                    characterInput.value = settings.character;
                }

                if (settings.character_info) {
                    characterInfoTextarea.value = settings.character_info;
                }

                if (settings.character_breakdown !== undefined) {
                    characterBreakdownCheckbox.checked = settings.character_breakdown;
                }

                // Set custom instructions
                const customInstructionsTextarea = document.getElementById('ai-custom-instructions');
                if (settings.custom_instructions) {
                    customInstructionsTextarea.value = settings.custom_instructions;
                }

                aiSettingsLoaded = true;
                displayFeedback('ai-settings-feedback', 'AI settings loaded successfully.');
            }
        } catch (error) {
            displayFeedback('ai-settings-feedback', `Error loading AI settings: ${error.message}`, true);
        }
    }

    // --- AI Settings Event Listeners ---

    // Temperature slider
    document.getElementById('ai-temperature').addEventListener('input', function() {
        document.getElementById('temperature-value').textContent = this.value;
    });

    // Reasoning checkbox
    document.getElementById('ai-reasoning-enabled').addEventListener('change', function() {
        document.getElementById('reasoning-effort-group').style.display = this.checked ? 'block' : 'none';
    });

    // Save AI Settings button
    document.getElementById('save-ai-settings-button').addEventListener('click', async () => {
        try {
            const settings = {
                model_id: document.getElementById('ai-model-select').value,
                temperature: parseFloat(document.getElementById('ai-temperature').value),
                max_tokens: parseInt(document.getElementById('ai-max-tokens').value),
                reasoning_enabled: document.getElementById('ai-reasoning-enabled').checked,
                reasoning_effort: document.getElementById('ai-reasoning-effort').value,
                web_search_enabled: document.getElementById('ai-web-search-enabled').checked
            };

            await fetchAPI('/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings })
            });

            displayFeedback('ai-settings-feedback', 'AI settings saved successfully!');
        } catch (error) {
            displayFeedback('ai-settings-feedback', `Error saving AI settings: ${error.message}`, true);
        }
    });

    // Reset AI Settings button
    document.getElementById('reset-ai-settings-button').addEventListener('click', async () => {
        if (!confirm('Are you sure you want to reset AI settings to defaults?')) return;

        try {
            const defaultSettings = {
                model_id: "openai/gpt-3.5-turbo",
                temperature: 0.7,
                max_tokens: 1000,
                reasoning_enabled: false,
                reasoning_effort: "medium",
                web_search_enabled: false
            };

            await fetchAPI('/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings: defaultSettings })
            });

            // Update UI with default values
            document.getElementById('ai-model-select').value = defaultSettings.model_id;
            document.getElementById('ai-temperature').value = defaultSettings.temperature;
            document.getElementById('temperature-value').textContent = defaultSettings.temperature;
            document.getElementById('ai-max-tokens').value = defaultSettings.max_tokens;
            document.getElementById('ai-reasoning-enabled').checked = defaultSettings.reasoning_enabled;
            document.getElementById('reasoning-effort-group').style.display = defaultSettings.reasoning_enabled ? 'block' : 'none';
            document.getElementById('ai-reasoning-effort').value = defaultSettings.reasoning_effort;
            document.getElementById('ai-web-search-enabled').checked = defaultSettings.web_search_enabled;

            displayFeedback('ai-settings-feedback', 'AI settings reset to defaults.');
        } catch (error) {
            displayFeedback('ai-settings-feedback', `Error resetting AI settings: ${error.message}`, true);
        }
    });

    // Save Character Settings button
    document.getElementById('save-character-settings-button').addEventListener('click', async () => {
        try {
            const settings = {
                character: document.getElementById('ai-character').value,
                character_info: document.getElementById('ai-character-info').value,
                character_breakdown: document.getElementById('ai-character-breakdown').checked
            };

            await fetchAPI('/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings })
            });

            displayFeedback('character-settings-feedback', 'Character settings saved successfully!');
        } catch (error) {
            displayFeedback('character-settings-feedback', `Error saving character settings: ${error.message}`, true);
        }
    });

    // Clear Character button
    document.getElementById('clear-character-settings-button').addEventListener('click', async () => {
        if (!confirm('Are you sure you want to clear character settings?')) return;

        try {
            const settings = {
                character: null,
                character_info: null,
                character_breakdown: false
            };

            await fetchAPI('/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings })
            });

            // Clear UI
            document.getElementById('ai-character').value = '';
            document.getElementById('ai-character-info').value = '';
            document.getElementById('ai-character-breakdown').checked = false;

            displayFeedback('character-settings-feedback', 'Character settings cleared.');
        } catch (error) {
            displayFeedback('character-settings-feedback', `Error clearing character settings: ${error.message}`, true);
        }
    });

    // Save System Prompt button
    document.getElementById('save-system-prompt-button').addEventListener('click', async () => {
        try {
            const settings = {
                system_message: document.getElementById('ai-system-prompt').value
            };

            await fetchAPI('/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings })
            });

            displayFeedback('system-prompt-feedback', 'System prompt saved successfully!');
        } catch (error) {
            displayFeedback('system-prompt-feedback', `Error saving system prompt: ${error.message}`, true);
        }
    });

    // Reset System Prompt button
    document.getElementById('reset-system-prompt-button').addEventListener('click', async () => {
        if (!confirm('Are you sure you want to reset the system prompt to default?')) return;

        try {
            const settings = {
                system_message: null
            };

            await fetchAPI('/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings })
            });

            // Clear UI
            document.getElementById('ai-system-prompt').value = '';

            displayFeedback('system-prompt-feedback', 'System prompt reset to default.');
        } catch (error) {
            displayFeedback('system-prompt-feedback', `Error resetting system prompt: ${error.message}`, true);
        }
    });

    // Save Custom Instructions button
    document.getElementById('save-custom-instructions-button').addEventListener('click', async () => {
        try {
            const settings = {
                custom_instructions: document.getElementById('ai-custom-instructions').value
            };

            await fetchAPI('/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings })
            });

            displayFeedback('custom-instructions-feedback', 'Custom instructions saved successfully!');
        } catch (error) {
            displayFeedback('custom-instructions-feedback', `Error saving custom instructions: ${error.message}`, true);
        }
    });

    // Clear Custom Instructions button
    document.getElementById('clear-custom-instructions-button').addEventListener('click', async () => {
        if (!confirm('Are you sure you want to clear custom instructions?')) return;

        try {
            const settings = {
                custom_instructions: null
            };

            await fetchAPI('/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings })
            });

            // Clear UI
            document.getElementById('ai-custom-instructions').value = '';

            displayFeedback('custom-instructions-feedback', 'Custom instructions cleared.');
        } catch (error) {
            displayFeedback('custom-instructions-feedback', `Error clearing custom instructions: ${error.message}`, true);
        }
    });

    // --- Conversations Functions ---
    let currentConversations = [];
    let selectedConversationId = null;

    async function loadConversations() {
        try {
            const response = await fetchAPI('/conversations');
            currentConversations = response.conversations || [];

            renderConversationsList();
            conversationsLoaded = true;

            if (currentConversations.length === 0) {
                // Show the "no conversations" message
                document.querySelector('.no-conversations').style.display = 'block';
                document.getElementById('conversation-detail').style.display = 'none';
            } else {
                document.querySelector('.no-conversations').style.display = 'none';
            }
        } catch (error) {
            console.error('Error loading conversations:', error);
            document.querySelector('.no-conversations').textContent = `Error loading conversations: ${error.message}`;
        }
    }

    function renderConversationsList() {
        const conversationsList = document.getElementById('conversations-list');
        const noConversationsMessage = document.querySelector('.no-conversations');

        // Clear existing conversations except the "no conversations" message
        Array.from(conversationsList.children).forEach(child => {
            if (!child.classList.contains('no-conversations')) {
                conversationsList.removeChild(child);
            }
        });

        if (currentConversations.length === 0) {
            noConversationsMessage.style.display = 'block';
            return;
        }

        noConversationsMessage.style.display = 'none';

        // Sort conversations by updated_at (newest first)
        const sortedConversations = [...currentConversations].sort((a, b) => {
            return new Date(b.updated_at) - new Date(a.updated_at);
        });

        // Add conversations to the list
        sortedConversations.forEach(conversation => {
            const conversationItem = document.createElement('div');
            conversationItem.className = 'conversation-item';
            conversationItem.dataset.id = conversation.id;

            if (conversation.id === selectedConversationId) {
                conversationItem.classList.add('active');
            }

            // Get the last message for preview
            let previewText = 'No messages';
            if (conversation.messages && conversation.messages.length > 0) {
                const lastMessage = conversation.messages[conversation.messages.length - 1];
                previewText = lastMessage.content.substring(0, 100) + (lastMessage.content.length > 100 ? '...' : '');
            }

            // Format the date
            const date = new Date(conversation.updated_at);
            const formattedDate = date.toLocaleDateString() + ' ' + date.toLocaleTimeString();

            conversationItem.innerHTML = `
                <div class="conversation-item-header">
                    <h4 class="conversation-title">${conversation.title}</h4>
                    <span class="conversation-date">${formattedDate}</span>
                </div>
                <div class="conversation-preview">${previewText}</div>
            `;

            conversationItem.addEventListener('click', () => {
                // Deselect previously selected conversation
                const previouslySelected = document.querySelector('.conversation-item.active');
                if (previouslySelected) {
                    previouslySelected.classList.remove('active');
                }

                // Select this conversation
                conversationItem.classList.add('active');
                selectedConversationId = conversation.id;

                // Show conversation details
                showConversationDetail(conversation);
            });

            conversationsList.appendChild(conversationItem);
        });
    }

    function showConversationDetail(conversation) {
        const conversationDetail = document.getElementById('conversation-detail');
        const conversationTitle = document.getElementById('conversation-title');
        const conversationMessages = document.getElementById('conversation-messages');

        // Show the detail section
        conversationDetail.style.display = 'block';

        // Set the title
        conversationTitle.textContent = conversation.title;

        // Clear existing messages
        conversationMessages.innerHTML = '';

        // Add messages
        if (conversation.messages && conversation.messages.length > 0) {
            conversation.messages.forEach(message => {
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${message.role === 'user' ? 'user-message' : 'ai-message'}`;

                messageDiv.innerHTML = `
                    <div class="message-header">${message.role === 'user' ? 'You' : 'AI'}</div>
                    <div class="message-content">${message.content}</div>
                `;

                conversationMessages.appendChild(messageDiv);
            });

            // Scroll to the bottom
            conversationMessages.scrollTop = conversationMessages.scrollHeight;
        } else {
            // No messages
            const emptyMessage = document.createElement('div');
            emptyMessage.className = 'no-messages';
            emptyMessage.textContent = 'This conversation has no messages.';
            conversationMessages.appendChild(emptyMessage);
        }
    }

    async function deleteConversation(conversationId) {
        try {
            await fetchAPI(`/conversations/${conversationId}`, {
                method: 'DELETE'
            });

            // Remove from the current conversations array
            currentConversations = currentConversations.filter(conv => conv.id !== conversationId);

            // If the deleted conversation was selected, clear the selection
            if (selectedConversationId === conversationId) {
                selectedConversationId = null;
                document.getElementById('conversation-detail').style.display = 'none';
            }

            // Re-render the list
            renderConversationsList();

            if (currentConversations.length === 0) {
                document.querySelector('.no-conversations').style.display = 'block';
            }

            return true;
        } catch (error) {
            console.error('Error deleting conversation:', error);
            return false;
        }
    }

    async function renameConversation(conversationId, newTitle) {
        try {
            // Find the conversation
            const conversation = currentConversations.find(conv => conv.id === conversationId);
            if (!conversation) {
                throw new Error('Conversation not found');
            }

            // Update the title
            conversation.title = newTitle;

            // Save to the server
            await fetchAPI('/conversations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ conversation })
            });

            // Re-render the list
            renderConversationsList();

            // Update the detail view if this conversation is selected
            if (selectedConversationId === conversationId) {
                document.getElementById('conversation-title').textContent = newTitle;
            }

            return true;
        } catch (error) {
            console.error('Error renaming conversation:', error);
            return false;
        }
    }

    async function createNewConversation(title) {
        try {
            // Create a new conversation object
            const newConversation = {
                id: crypto.randomUUID ? crypto.randomUUID() : `conv-${Date.now()}`,
                title: title || 'New Conversation',
                messages: [],
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            };

            // Save to the server
            const savedConversation = await fetchAPI('/conversations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ conversation: newConversation })
            });

            // Add to the current conversations array
            currentConversations.push(savedConversation);

            // Re-render the list
            renderConversationsList();

            // Select the new conversation
            selectedConversationId = savedConversation.id;
            showConversationDetail(savedConversation);

            // Hide the "no conversations" message
            document.querySelector('.no-conversations').style.display = 'none';

            return savedConversation;
        } catch (error) {
            console.error('Error creating conversation:', error);
            return null;
        }
    }

    function exportConversation(conversation) {
        // Create a JSON string of the conversation
        const conversationJson = JSON.stringify(conversation, null, 2);

        // Create a blob with the JSON data
        const blob = new Blob([conversationJson], { type: 'application/json' });

        // Create a URL for the blob
        const url = URL.createObjectURL(blob);

        // Create a temporary link element
        const link = document.createElement('a');
        link.href = url;
        link.download = `conversation-${conversation.id}.json`;

        // Append the link to the body
        document.body.appendChild(link);

        // Click the link to trigger the download
        link.click();

        // Clean up
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }

    // --- Conversation Event Listeners ---

    // New Conversation button
    document.getElementById('new-conversation-button').addEventListener('click', () => {
        // Show the new conversation modal
        const modal = document.getElementById('new-conversation-modal');
        modal.style.display = 'block';

        // Focus the input
        document.getElementById('new-conversation-name').focus();
    });

    // Create Conversation button (in modal)
    document.getElementById('create-conversation-button').addEventListener('click', async () => {
        const title = document.getElementById('new-conversation-name').value.trim() || 'New Conversation';
        const newConversation = await createNewConversation(title);

        if (newConversation) {
            // Close the modal
            document.getElementById('new-conversation-modal').style.display = 'none';

            // Clear the input
            document.getElementById('new-conversation-name').value = '';
        }
    });

    // Cancel Create button (in modal)
    document.getElementById('cancel-create-button').addEventListener('click', () => {
        // Close the modal
        document.getElementById('new-conversation-modal').style.display = 'none';

        // Clear the input
        document.getElementById('new-conversation-name').value = '';
    });

    // Close modal buttons
    document.querySelectorAll('.close-modal').forEach(closeButton => {
        closeButton.addEventListener('click', () => {
            // Find the parent modal
            const modal = closeButton.closest('.modal');
            modal.style.display = 'none';
        });
    });

    // Delete Conversation button
    document.getElementById('delete-conversation-button').addEventListener('click', async () => {
        if (!selectedConversationId) return;

        if (confirm('Are you sure you want to delete this conversation? This action cannot be undone.')) {
            const success = await deleteConversation(selectedConversationId);

            if (success) {
                // Hide the detail view
                document.getElementById('conversation-detail').style.display = 'none';
            } else {
                alert('Failed to delete conversation. Please try again.');
            }
        }
    });

    // Rename Conversation button
    document.getElementById('rename-conversation-button').addEventListener('click', () => {
        if (!selectedConversationId) return;

        // Show the rename modal
        const modal = document.getElementById('rename-modal');
        modal.style.display = 'block';

        // Set the current title as the default value
        const conversation = currentConversations.find(conv => conv.id === selectedConversationId);
        if (conversation) {
            document.getElementById('new-conversation-title').value = conversation.title;
        }

        // Focus the input
        document.getElementById('new-conversation-title').focus();
    });

    // Confirm Rename button (in modal)
    document.getElementById('confirm-rename-button').addEventListener('click', async () => {
        if (!selectedConversationId) return;

        const newTitle = document.getElementById('new-conversation-title').value.trim();
        if (!newTitle) {
            alert('Please enter a title for the conversation.');
            return;
        }

        const success = await renameConversation(selectedConversationId, newTitle);

        if (success) {
            // Close the modal
            document.getElementById('rename-modal').style.display = 'none';
        } else {
            alert('Failed to rename conversation. Please try again.');
        }
    });

    // Cancel Rename button (in modal)
    document.getElementById('cancel-rename-button').addEventListener('click', () => {
        // Close the modal
        document.getElementById('rename-modal').style.display = 'none';
    });

    // Export Conversation button
    document.getElementById('export-conversation-button').addEventListener('click', () => {
        if (!selectedConversationId) return;

        const conversation = currentConversations.find(conv => conv.id === selectedConversationId);
        if (conversation) {
            exportConversation(conversation);
        }
    });

    // Conversation Search
    document.getElementById('conversation-search').addEventListener('input', function() {
        const searchTerm = this.value.toLowerCase().trim();

        if (!searchTerm) {
            // If search is empty, show all conversations
            renderConversationsList();
            return;
        }

        // Filter conversations by title and content
        const filteredConversations = currentConversations.filter(conversation => {
            // Check title
            if (conversation.title.toLowerCase().includes(searchTerm)) {
                return true;
            }

            // Check message content
            if (conversation.messages && conversation.messages.length > 0) {
                return conversation.messages.some(message =>
                    message.content.toLowerCase().includes(searchTerm)
                );
            }

            return false;
        });

        // Update the current conversations array temporarily for rendering
        const originalConversations = currentConversations;
        currentConversations = filteredConversations;

        // Render the filtered list
        renderConversationsList();

        // Restore the original conversations array
        currentConversations = originalConversations;
    });

    // --- Initial Load ---
    let aiSettingsLoaded = false;
    let conversationsLoaded = false;

    checkLoginStatus();
});
