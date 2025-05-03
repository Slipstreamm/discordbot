document.addEventListener('DOMContentLoaded', () => {
    const loginButton = document.getElementById('login-button');
    const logoutButton = document.getElementById('logout-button');
    const authSection = document.getElementById('auth-section');
    const dashboardSection = document.getElementById('dashboard-section');
    const usernameSpan = document.getElementById('username');
    const guildSelect = document.getElementById('guild-select');
    const settingsForm = document.getElementById('settings-form');

    // --- API Base URL (Adjust if needed) ---
    // Assuming the API runs on the same host/port for simplicity,
    // otherwise, use the full URL like 'http://localhost:8000'
    const API_BASE_URL = '/api'; // Relative path if served by the same server

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
        window.location.href = `${API_BASE_URL}/auth/login`;
    });

    logoutButton.addEventListener('click', async () => {
        try {
            await fetchAPI('/auth/logout', { method: 'POST' });
            showLogin();
        } catch (error) {
            alert('Logout failed. Please try again.');
        }
    });

    // --- Guild Loading and Settings ---
    async function loadGuilds() {
        try {
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
        // Clear previous settings?
        document.getElementById('prefix-input').value = '';
        document.getElementById('welcome-channel').innerHTML = '';
        document.getElementById('welcome-message').value = '';
        document.getElementById('goodbye-channel').innerHTML = '';
        document.getElementById('goodbye-message').value = '';
        document.getElementById('cogs-list').innerHTML = '';

        try {
            const settings = await fetchAPI(`/guilds/${guildId}/settings`);
            console.log("Received settings:", settings);

            // Populate Prefix
            document.getElementById('prefix-input').value = settings.prefix || '';

            // Populate Welcome/Goodbye IDs (Dropdown population is not feasible from API alone)
            // We'll just display the ID if set, or allow input? Let's stick to the select for now,
            // but it won't be populated dynamically. The user needs to know the channel ID.
            // We can pre-select the stored value if it exists.
            const wcSelect = document.getElementById('welcome-channel');
            wcSelect.innerHTML = '<option value="">-- Select Channel --</option>'; // Clear previous options
            if (settings.welcome_channel_id) {
                // Add the stored ID as an option, maybe mark it as potentially invalid if needed
                 const option = document.createElement('option');
                 option.value = settings.welcome_channel_id;
                 option.textContent = `#? (ID: ${settings.welcome_channel_id})`; // Indicate it's just the ID
                 option.selected = true;
                 wcSelect.appendChild(option);
            }
            document.getElementById('welcome-message').value = settings.welcome_message || '';

            const gcSelect = document.getElementById('goodbye-channel');
            gcSelect.innerHTML = '<option value="">-- Select Channel --</option>'; // Clear previous options
             if (settings.goodbye_channel_id) {
                 const option = document.createElement('option');
                 option.value = settings.goodbye_channel_id;
                 option.textContent = `#? (ID: ${settings.goodbye_channel_id})`;
                 option.selected = true;
                 gcSelect.appendChild(option);
             }
            document.getElementById('goodbye-message').value = settings.goodbye_message || '';

            // Populate Cogs - This will only show cogs whose state is known by the API/DB
            // It won't show all possible cogs unless the API is enhanced.
            populateCogsList(settings.enabled_cogs || {}); // Use the correct field name

        } catch (error) {
             displayFeedback('prefix-feedback', `Error loading settings: ${error.message}`, true); // Use a general feedback area?
        }
    }

    // Removed populateChannelSelect as dynamic population isn't feasible from API alone.
    // Users will need to manage channel IDs directly for now.

     function populateCogsList(cogsStatus) {
        // This function now only displays cogs whose status is stored in the DB
        // and returned by the API. It doesn't know about *all* possible cogs.
        const cogsListDiv = document.getElementById('cogs-list');
        cogsListDiv.innerHTML = ''; // Clear previous
        // Assuming CORE_COGS is available globally or passed somehow
        const CORE_COGS = ['SettingsCog', 'HelpCog']; // Example - needs to match backend

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


    // --- Save Settings Event Listeners ---

    document.getElementById('save-prefix-button').addEventListener('click', async () => {
        const guildId = guildSelect.value;
        const prefix = document.getElementById('prefix-input').value;
        if (!guildId) return;

        try {
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
        // Get channel ID directly. Assume user inputs/knows the ID.
        // We might change the input type from select later if this is confusing.
        const channelIdInput = document.getElementById('welcome-channel').value; // Treat select as input for now
        const message = document.getElementById('welcome-message').value;
        if (!guildId) return;

        // Basic validation for channel ID (numeric)
        const channelId = channelIdInput && /^\d+$/.test(channelIdInput) ? channelIdInput : null;

        try {
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
        const channelIdInput = document.getElementById('goodbye-channel').value; // Treat select as input
        const message = document.getElementById('goodbye-message').value;
        if (!guildId) return;

        const channelId = channelIdInput && /^\d+$/.test(channelIdInput) ? channelIdInput : null;

        try {
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


    // --- Initial Load ---
    checkLoginStatus();
});
