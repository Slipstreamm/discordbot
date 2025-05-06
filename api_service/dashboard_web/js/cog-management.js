/**
 * Cog Management JavaScript
 * Handles cog and command enabling/disabling functionality
 */

// Global variables
let cogsData = [];
let commandsData = {};
let selectedGuildId = null;
let cogManagementLoaded = false;

// Initialize cog management when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    initCogManagement();
});

/**
 * Initialize cog management functionality
 */
function initCogManagement() {
    // Get DOM elements
    const cogGuildSelect = document.getElementById('cog-guild-select');
    const cogFilter = document.getElementById('cog-filter');
    const saveCogsButton = document.getElementById('save-cogs-button');
    const saveCommandsButton = document.getElementById('save-commands-button');
    const navCogManagement = document.getElementById('nav-cog-management');

    // Add event listener for cog management tab
    if (navCogManagement) {
        navCogManagement.addEventListener('click', () => {
            // Show cog management section
            showSection('cog-management');

            // Load guilds if not already loaded
            if (!cogManagementLoaded) {
                loadGuildsForCogManagement();
                cogManagementLoaded = true;
            }
        });
    }

    // Add event listener for guild select
    if (cogGuildSelect) {
        cogGuildSelect.addEventListener('change', () => {
            selectedGuildId = cogGuildSelect.value;
            if (selectedGuildId) {
                loadCogsAndCommands(selectedGuildId);
            } else {
                // Hide content if no guild selected
                document.getElementById('cog-management-content').style.display = 'none';
            }
        });
    }

    // Add event listener for cog filter
    if (cogFilter) {
        cogFilter.addEventListener('change', () => {
            filterCommands(cogFilter.value);
        });
    }

    // Add event listener for save cogs button
    if (saveCogsButton) {
        saveCogsButton.addEventListener('click', () => {
            saveCogsSettings();
        });
    }

    // Add event listener for save commands button
    if (saveCommandsButton) {
        saveCommandsButton.addEventListener('click', () => {
            saveCommandsSettings();
        });
    }
}

/**
 * Load guilds for cog management
 */
function loadGuildsForCogManagement() {
    const cogGuildSelect = document.getElementById('cog-guild-select');

    // Show loading state
    cogGuildSelect.disabled = true;
    cogGuildSelect.innerHTML = '<option value="">Loading servers...</option>';

    // Fetch guilds from API
    API.get('/dashboard/api/guilds')
        .then(guilds => {
            // Clear loading state
            cogGuildSelect.innerHTML = '<option value="">--Please choose a server--</option>';

            // Add guilds to select
            guilds.forEach(guild => {
                const option = document.createElement('option');
                option.value = guild.id;
                option.textContent = guild.name;
                cogGuildSelect.appendChild(option);
            });

            // Enable select
            cogGuildSelect.disabled = false;
        })
        .catch(error => {
            console.error('Error loading guilds:', error);
            cogGuildSelect.innerHTML = '<option value="">Error loading servers</option>';
            cogGuildSelect.disabled = false;
            Toast.error('Failed to load servers. Please try again.');
        });
}

/**
 * Load cogs and commands for a guild
 * @param {string} guildId - The guild ID
 */
function loadCogsAndCommands(guildId) {
    // Show loading state
    document.getElementById('cog-management-loading').style.display = 'flex';
    document.getElementById('cog-management-content').style.display = 'none';

    // Fetch cogs and commands from API
    console.log(`Loading cogs and commands for guild ${guildId}...`);
    API.get(`/dashboard/api/guilds/${guildId}/cogs`)
        .then(data => {
            console.log('Cogs and commands loaded successfully:', data);
            // Store data
            cogsData = data;

            // Populate cogs list
            populateCogsUI(data);

            // Populate commands list
            populateCommandsUI(data);

            // Hide loading state
            document.getElementById('cog-management-loading').style.display = 'none';
            document.getElementById('cog-management-content').style.display = 'block';
        })
        .catch(error => {
            console.error('Error loading cogs and commands:', error);
            document.getElementById('cog-management-loading').style.display = 'none';
            Toast.error('Failed to load cogs and commands. Please try again.');
        });
}

/**
 * Populate cogs UI
 * @param {Array} cogs - Array of cog objects
 */
function populateCogsUI(cogs) {
    const cogsList = document.getElementById('cogs-list');
    const cogFilter = document.getElementById('cog-filter');

    // Clear previous content
    cogsList.innerHTML = '';

    // Clear filter options except "All Cogs"
    cogFilter.innerHTML = '<option value="all">All Cogs</option>';

    // Add cogs to list
    cogs.forEach(cog => {
        // Create cog card
        const cogCard = document.createElement('div');
        cogCard.className = 'cog-card p-4 border rounded';

        // Create cog header
        const cogHeader = document.createElement('div');
        cogHeader.className = 'cog-header flex items-center justify-between mb-2';

        // Create cog checkbox
        const cogCheckbox = document.createElement('div');
        cogCheckbox.className = 'cog-checkbox flex items-center';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = `cog-${cog.name}`;
        checkbox.className = 'mr-2';
        checkbox.checked = cog.enabled;
        checkbox.dataset.cogName = cog.name;

        // Disable checkbox for core cogs
        if (cog.name === 'SettingsCog' || cog.name === 'HelpCog') {
            checkbox.disabled = true;
            checkbox.title = 'Core cogs cannot be disabled';
        }

        const label = document.createElement('label');
        label.htmlFor = `cog-${cog.name}`;
        label.textContent = cog.name;
        label.className = 'font-medium';

        cogCheckbox.appendChild(checkbox);
        cogCheckbox.appendChild(label);

        // Create command count badge
        const commandCount = document.createElement('span');
        commandCount.className = 'command-count bg-gray-200 text-gray-800 px-2 py-1 rounded text-xs';
        commandCount.textContent = `${cog.commands.length} commands`;

        cogHeader.appendChild(cogCheckbox);
        cogHeader.appendChild(commandCount);

        // Create cog description
        const cogDescription = document.createElement('p');
        cogDescription.className = 'cog-description text-sm text-gray-600 mt-1';
        cogDescription.textContent = cog.description || 'No description available';

        // Add elements to cog card
        cogCard.appendChild(cogHeader);
        cogCard.appendChild(cogDescription);

        // Add cog card to list
        cogsList.appendChild(cogCard);

        // Add cog to filter options
        const option = document.createElement('option');
        option.value = cog.name;
        option.textContent = cog.name;
        cogFilter.appendChild(option);
    });
}

/**
 * Populate commands UI
 * @param {Array} cogs - Array of cog objects
 */
function populateCommandsUI(cogs) {
    const commandsList = document.getElementById('commands-list');

    // Clear previous content
    commandsList.innerHTML = '';

    // Create a flat list of all commands with their cog
    commandsData = {};

    cogs.forEach(cog => {
        cog.commands.forEach(command => {
            // Store command data with cog name
            commandsData[command.name] = {
                ...command,
                cog_name: cog.name
            };

            // Create command card
            const commandCard = createCommandCard(command, cog.name);

            // Add command card to list
            commandsList.appendChild(commandCard);
        });
    });
}

/**
 * Create a command card element
 * @param {Object} command - Command object
 * @param {string} cogName - Name of the cog the command belongs to
 * @returns {HTMLElement} Command card element
 */
function createCommandCard(command, cogName) {
    // Create command card
    const commandCard = document.createElement('div');
    commandCard.className = 'command-card p-4 border rounded';
    commandCard.dataset.cogName = cogName;

    // Create command header
    const commandHeader = document.createElement('div');
    commandHeader.className = 'command-header flex items-center justify-between mb-2';

    // Create command checkbox
    const commandCheckbox = document.createElement('div');
    commandCheckbox.className = 'command-checkbox flex items-center';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = `command-${command.name}`;
    checkbox.className = 'mr-2';
    checkbox.checked = command.enabled;
    checkbox.dataset.commandName = command.name;

    const label = document.createElement('label');
    label.htmlFor = `command-${command.name}`;
    label.textContent = command.name;
    label.className = 'font-medium';

    commandCheckbox.appendChild(checkbox);
    commandCheckbox.appendChild(label);

    // Create cog badge
    const cogBadge = document.createElement('span');
    cogBadge.className = 'cog-badge bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs';
    cogBadge.textContent = cogName;

    commandHeader.appendChild(commandCheckbox);
    commandHeader.appendChild(cogBadge);

    // Create command description
    const commandDescription = document.createElement('p');
    commandDescription.className = 'command-description text-sm text-gray-600 mt-1';
    commandDescription.textContent = command.description || 'No description available';

    // Add elements to command card
    commandCard.appendChild(commandHeader);
    commandCard.appendChild(commandDescription);

    return commandCard;
}

/**
 * Filter commands by cog
 * @param {string} cogName - Name of the cog to filter by, or "all" for all cogs
 */
function filterCommands(cogName) {
    const commandCards = document.querySelectorAll('.command-card');

    commandCards.forEach(card => {
        if (cogName === 'all' || card.dataset.cogName === cogName) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

/**
 * Save cogs settings
 */
function saveCogsSettings() {
    if (!selectedGuildId) return;

    // Show loading state
    const saveButton = document.getElementById('save-cogs-button');
    saveButton.disabled = true;
    saveButton.textContent = 'Saving...';

    // Get cog settings
    const cogsPayload = {};
    const cogCheckboxes = document.querySelectorAll('#cogs-list input[type="checkbox"]');

    cogCheckboxes.forEach(checkbox => {
        if (!checkbox.disabled) {
            cogsPayload[checkbox.dataset.cogName] = checkbox.checked;
        }
    });

    // Send request to API
    API.patch(`/dashboard/api/guilds/${selectedGuildId}/settings`, {
        cogs: cogsPayload
    })
        .then(() => {
            // Reset button state
            saveButton.disabled = false;
            saveButton.textContent = 'Save Cog Settings';

            // Show success message
            document.getElementById('cogs-feedback').textContent = 'Cog settings saved successfully!';
            document.getElementById('cogs-feedback').className = 'mt-2 text-green-600';

            // Clear message after 3 seconds
            setTimeout(() => {
                document.getElementById('cogs-feedback').textContent = '';
                document.getElementById('cogs-feedback').className = 'mt-2';
            }, 3000);

            Toast.success('Cog settings saved successfully!');
        })
        .catch(error => {
            console.error('Error saving cog settings:', error);

            // Reset button state
            saveButton.disabled = false;
            saveButton.textContent = 'Save Cog Settings';

            // Show error message
            document.getElementById('cogs-feedback').textContent = 'Error saving cog settings. Please try again.';
            document.getElementById('cogs-feedback').className = 'mt-2 text-red-600';

            Toast.error('Failed to save cog settings. Please try again.');
        });
}

/**
 * Save commands settings
 */
function saveCommandsSettings() {
    if (!selectedGuildId) return;

    // Show loading state
    const saveButton = document.getElementById('save-commands-button');
    saveButton.disabled = true;
    saveButton.textContent = 'Saving...';

    // Get command settings
    const commandsPayload = {};
    const commandCheckboxes = document.querySelectorAll('#commands-list input[type="checkbox"]');

    commandCheckboxes.forEach(checkbox => {
        commandsPayload[checkbox.dataset.commandName] = checkbox.checked;
    });

    // Send request to API
    API.patch(`/dashboard/api/guilds/${selectedGuildId}/settings`, {
        commands: commandsPayload
    })
        .then(() => {
            // Reset button state
            saveButton.disabled = false;
            saveButton.textContent = 'Save Command Settings';

            // Show success message
            document.getElementById('commands-feedback').textContent = 'Command settings saved successfully!';
            document.getElementById('commands-feedback').className = 'mt-2 text-green-600';

            // Clear message after 3 seconds
            setTimeout(() => {
                document.getElementById('commands-feedback').textContent = '';
                document.getElementById('commands-feedback').className = 'mt-2';
            }, 3000);

            Toast.success('Command settings saved successfully!');
        })
        .catch(error => {
            console.error('Error saving command settings:', error);

            // Reset button state
            saveButton.disabled = false;
            saveButton.textContent = 'Save Command Settings';

            // Show error message
            document.getElementById('commands-feedback').textContent = 'Error saving command settings. Please try again.';
            document.getElementById('commands-feedback').className = 'mt-2 text-red-600';

            Toast.error('Failed to save command settings. Please try again.');
        });
}
