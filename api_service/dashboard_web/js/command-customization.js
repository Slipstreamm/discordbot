/**
 * Command Customization JavaScript
 * Handles command customization functionality for the dashboard
 */

// Track loaded state
let commandCustomizationLoadedGuild = null;

// Initialize command customization when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    initCommandCustomization();
});

/**
 * Initialize command customization
 */
function initCommandCustomization() {
    // Add event listener to command search input
    const commandSearch = document.getElementById('command-search');
    if (commandSearch) {
        commandSearch.addEventListener('input', filterCommands);
    }

    // Add event listener to sync commands button
    const syncCommandsButton = document.getElementById('sync-commands-button');
    if (syncCommandsButton) {
        syncCommandsButton.addEventListener('click', syncCommands);
    }

    // Add event listener to add alias button
    const addAliasButton = document.getElementById('add-alias-button');
    if (addAliasButton) {
        addAliasButton.addEventListener('click', addAlias);
    }

    // Loading is now handled by showSection in main.js
    // const navItem = document.querySelector('a[data-section="command-customization-section"]');
    // if (navItem) {
    //     navItem.addEventListener('click', () => {
    //         loadCommandCustomizationData(window.selectedGuildId); // Pass guildId
    //     });
    // }
}

/**
 * Load command customizations from API
 * @param {string} guildId - The guild ID (passed from main.js)
 */
async function loadCommandCustomizationData(guildId) { // Renamed function
    // Track loaded state for this module
    if (commandCustomizationLoadedGuild === guildId) {
        console.log(`Command customization data for guild ${guildId} already loaded.`);
        // Ensure content is visible if navigating back
        document.getElementById('command-list').style.display = 'block';
        document.getElementById('group-list').style.display = 'block';
        document.getElementById('alias-list').style.display = 'block';
        return;
    }
    console.log(`Loading command customization data for guild: ${guildId}`);

    try {
        // Show loading spinners
        document.getElementById('command-list').innerHTML = '<div class="loading-spinner-container"><div class="loading-spinner"></div></div>';
        document.getElementById('group-list').innerHTML = '<div class="loading-spinner-container"><div class="loading-spinner"></div></div>';
        document.getElementById('alias-list').innerHTML = '<div class="loading-spinner-container"><div class="loading-spinner"></div></div>';

        if (!guildId) {
            Toast.error('No guild selected for command customization.');
            return;
        }

        // Fetch command customizations from API using the API helper
        const data = await API.get(`/dashboard/api/guilds/${guildId}/command-customizations`); // Updated endpoint

        // Render command customizations
        renderCommandCustomizations(data.command_customizations || {});

        // Render group customizations
        renderGroupCustomizations(data.group_customizations || {});

        // Render command aliases
        renderCommandAliases(data.command_aliases || {});

        // Populate command select for aliases
        populateCommandSelect(Object.keys(data.command_customizations || {}));

        // Mark as loaded for this guild
        commandCustomizationLoadedGuild = guildId;
    } catch (error) {
        console.error('Error loading command customizations:', error);
        Toast.error('Failed to load command customizations');

        // Show error message in lists
        document.getElementById('command-list').innerHTML = '<div class="alert alert-danger">Failed to load command customizations</div>';
        document.getElementById('group-list').innerHTML = '<div class="alert alert-danger">Failed to load group customizations</div>';
        document.getElementById('alias-list').innerHTML = '<div class="alert alert-danger">Failed to load command aliases</div>';
    }
}

/**
 * Render command customizations
 * @param {Object} commandCustomizations - Command customizations object
 */
function renderCommandCustomizations(commandCustomizations) {
    const commandList = document.getElementById('command-list');
    commandList.innerHTML = '';

    if (Object.keys(commandCustomizations).length === 0) {
        commandList.innerHTML = '<div class="alert alert-info">No commands found or available for customization.</div>';
        return;
    }

    // Sort commands alphabetically
    const sortedCommands = Object.keys(commandCustomizations).sort();

    // Create command items
    sortedCommands.forEach(commandName => {
        const customization = commandCustomizations[commandName];
        const commandItem = createCommandItem(commandName, customization);
        commandList.appendChild(commandItem);
    });
}

/**
 * Create a command item element
 * @param {string} commandName - Original command name
 * @param {Object} customization - Command customization object
 * @returns {HTMLElement} Command item element
 */
function createCommandItem(commandName, customization) {
    // Clone the template
    const template = document.getElementById('command-item-template');
    const commandItem = template.content.cloneNode(true).querySelector('.command-item');

    // Set command name
    const nameElement = commandItem.querySelector('.command-name');
    nameElement.textContent = commandName;
    if (customization.name && customization.name !== commandName) {
        nameElement.textContent = `${customization.name} (${commandName})`;
    }

    // Set command description
    const descriptionElement = commandItem.querySelector('.command-description');
    descriptionElement.textContent = customization.description || 'No description available';

    // Set custom name input value
    const customNameInput = commandItem.querySelector('.custom-command-name');
    customNameInput.value = customization.name || '';
    customNameInput.placeholder = commandName;

    // Set custom description input value
    const customDescriptionInput = commandItem.querySelector('.custom-command-description');
    customDescriptionInput.value = customization.description || '';

    // Add event listeners to buttons
    const editButton = commandItem.querySelector('.edit-command-btn');
    const resetButton = commandItem.querySelector('.reset-command-btn');
    const saveButton = commandItem.querySelector('.save-command-btn');
    const cancelButton = commandItem.querySelector('.cancel-command-btn');
    const customizationDiv = commandItem.querySelector('.command-customization');

    editButton.addEventListener('click', () => {
        customizationDiv.style.display = 'block';
        editButton.style.display = 'none';
    });

    resetButton.addEventListener('click', () => {
        resetCommandCustomization(commandName);
    });

    saveButton.addEventListener('click', () => {
        saveCommandCustomization(
            commandName,
            customNameInput.value,
            customDescriptionInput.value,
            customizationDiv,
            editButton,
            nameElement,
            descriptionElement
        );
    });

    cancelButton.addEventListener('click', () => {
        customizationDiv.style.display = 'none';
        editButton.style.display = 'inline-block';

        // Reset input values
        customNameInput.value = customization.name || '';
        customDescriptionInput.value = customization.description || '';
    });

    // Add data attribute for filtering
    commandItem.dataset.commandName = commandName.toLowerCase();

    return commandItem;
}

/**
 * Save command customization
 * @param {string} commandName - Original command name
 * @param {string} customName - Custom command name
 * @param {string} customDescription - Custom command description
 * @param {HTMLElement} customizationDiv - Command customization div
 * @param {HTMLElement} editButton - Edit button
 * @param {HTMLElement} nameElement - Command name element
 * @param {HTMLElement} descriptionElement - Command description element
 */
async function saveCommandCustomization(
    commandName,
    customName,
    customDescription,
    customizationDiv,
    editButton,
    nameElement,
    descriptionElement
) {
    try {
        // Validate custom name format if provided
        if (customName && (!/^[a-z][a-z0-9_]*$/.test(customName) || customName.length > 32)) {
            Toast.error('Custom command names must be lowercase, start with a letter, and contain only letters, numbers, and underscores (max 32 characters)');
            return;
        }

        // Validate custom description if provided
        if (customDescription && customDescription.length > 100) {
            Toast.error('Custom command descriptions must be 100 characters or less');
            return;
        }

        // Get the current guild ID
        const guildId = window.selectedGuildId; // Use global guild ID
        if (!guildId) {
            Toast.error('No guild selected');
            return;
        }

        // Prepare request data
        const requestData = {
            command_name: commandName,
            custom_name: customName || null,
            custom_description: customDescription || null
        };

        // Send request to API
        await API.post(`/dashboard/api/guilds/${guildId}/command-customizations/commands`, requestData); // Updated endpoint

        // Update UI
        customizationDiv.style.display = 'none';
        editButton.style.display = 'inline-block';

        if (customName) {
            nameElement.textContent = `${customName} (${commandName})`;
        } else {
            nameElement.textContent = commandName;
        }

        if (customDescription) {
            descriptionElement.textContent = customDescription;
        } else {
            // Fetch the original description if resetting
            // This might require an extra API call or storing original data
            descriptionElement.textContent = 'No description available'; // Placeholder
        }

        Toast.success('Command customization saved successfully');
    } catch (error) {
        console.error('Error saving command customization:', error);
        Toast.error(`Failed to save command customization: ${error.message || error}`);
    }
}

/**
 * Reset command customization
 * @param {string} commandName - Original command name
 */
async function resetCommandCustomization(commandName) {
    try {
        // Get the current guild ID
        const guildId = window.selectedGuildId; // Use global guild ID
        if (!guildId) {
            Toast.error('No guild selected');
            return;
        }

        // Prepare request data
        const requestData = {
            command_name: commandName,
            custom_name: null,
            custom_description: null
        };

        // Send request to API
        await API.post(`/dashboard/api/guilds/${guildId}/command-customizations/commands`, requestData); // Updated endpoint

        // Reload command customizations
        loadCommandCustomizationData(guildId); // Reload data for the current guild

        Toast.success('Command customization reset successfully');
    } catch (error) {
        console.error('Error resetting command customization:', error);
        Toast.error(`Failed to reset command customization: ${error.message || error}`);
    }
}

/**
 * Render group customizations
 * @param {Object} groupCustomizations - Group customizations object
 */
function renderGroupCustomizations(groupCustomizations) {
    const groupList = document.getElementById('group-list');
    groupList.innerHTML = '';

    if (Object.keys(groupCustomizations).length === 0) {
        groupList.innerHTML = '<div class="alert alert-info">No command groups found or available for customization.</div>';
        return;
    }

    // Sort groups alphabetically
    const sortedGroups = Object.keys(groupCustomizations).sort();

    // Create group items
    sortedGroups.forEach(groupName => {
        const customName = groupCustomizations[groupName];
        const groupItem = createGroupItem(groupName, customName);
        groupList.appendChild(groupItem);
    });
}

/**
 * Create a group item element
 * @param {string} groupName - Original group name
 * @param {string} customName - Custom group name
 * @returns {HTMLElement} Group item element
 */
function createGroupItem(groupName, customName) {
    // Clone the template
    const template = document.getElementById('group-item-template');
    const groupItem = template.content.cloneNode(true).querySelector('.command-item');

    // Set group name
    const nameElement = groupItem.querySelector('.group-name');
    nameElement.textContent = groupName;
    if (customName && customName !== groupName) {
        nameElement.textContent = `${customName} (${groupName})`;
    }

    // Set custom name input value
    const customNameInput = groupItem.querySelector('.custom-group-name');
    customNameInput.value = customName || '';
    customNameInput.placeholder = groupName;

    // Add event listeners to buttons
    const editButton = groupItem.querySelector('.edit-group-btn');
    const resetButton = groupItem.querySelector('.reset-group-btn');
    const saveButton = groupItem.querySelector('.save-group-btn');
    const cancelButton = groupItem.querySelector('.cancel-group-btn');
    const customizationDiv = groupItem.querySelector('.group-customization');

    editButton.addEventListener('click', () => {
        customizationDiv.style.display = 'block';
        editButton.style.display = 'none';
    });

    resetButton.addEventListener('click', () => {
        resetGroupCustomization(groupName);
    });

    saveButton.addEventListener('click', () => {
        saveGroupCustomization(
            groupName,
            customNameInput.value,
            customizationDiv,
            editButton,
            nameElement
        );
    });

    cancelButton.addEventListener('click', () => {
        customizationDiv.style.display = 'none';
        editButton.style.display = 'inline-block';

        // Reset input value
        customNameInput.value = customName || '';
    });

    return groupItem;
}

/**
 * Save group customization
 * @param {string} groupName - Original group name
 * @param {string} customName - Custom group name
 * @param {HTMLElement} customizationDiv - Group customization div
 * @param {HTMLElement} editButton - Edit button
 * @param {HTMLElement} nameElement - Group name element
 */
async function saveGroupCustomization(
    groupName,
    customName,
    customizationDiv,
    editButton,
    nameElement
) {
    try {
        // Validate custom name format if provided
        if (customName && (!/^[a-z][a-z0-9_]*$/.test(customName) || customName.length > 32)) {
            Toast.error('Custom group names must be lowercase, start with a letter, and contain only letters, numbers, and underscores (max 32 characters)');
            return;
        }

        // Get the current guild ID
        const guildId = window.selectedGuildId; // Use global guild ID
        if (!guildId) {
            Toast.error('No guild selected');
            return;
        }

        // Prepare request data
        const requestData = {
            group_name: groupName,
            custom_name: customName || null
        };

        // Send request to API
        await API.post(`/dashboard/api/guilds/${guildId}/command-customizations/groups`, requestData); // Updated endpoint

        // Update UI
        customizationDiv.style.display = 'none';
        editButton.style.display = 'inline-block';

        if (customName) {
            nameElement.textContent = `${customName} (${groupName})`;
        } else {
            nameElement.textContent = groupName;
        }

        Toast.success('Group customization saved successfully');
    } catch (error) {
        console.error('Error saving group customization:', error);
        Toast.error(`Failed to save group customization: ${error.message || error}`);
    }
}

/**
 * Reset group customization
 * @param {string} groupName - Original group name
 */
async function resetGroupCustomization(groupName) {
    try {
        // Get the current guild ID
        const guildId = window.selectedGuildId; // Use global guild ID
        if (!guildId) {
            Toast.error('No guild selected');
            return;
        }

        // Prepare request data
        const requestData = {
            group_name: groupName,
            custom_name: null
        };

        // Send request to API
        await API.post(`/dashboard/api/guilds/${guildId}/command-customizations/groups`, requestData); // Updated endpoint

        // Reload command customizations
        loadCommandCustomizationData(guildId); // Reload data for the current guild

        Toast.success('Group customization reset successfully');
    } catch (error) {
        console.error('Error resetting group customization:', error);
        Toast.error(`Failed to reset group customization: ${error.message || error}`);
    }
}

/**
 * Render command aliases
 * @param {Object} commandAliases - Command aliases object
 */
function renderCommandAliases(commandAliases) {
    const aliasList = document.getElementById('alias-list');
    aliasList.innerHTML = '';

    if (Object.keys(commandAliases).length === 0) {
        aliasList.innerHTML = '<div class="alert alert-info">No command aliases found.</div>';
        return;
    }

    // Sort commands alphabetically
    const sortedCommands = Object.keys(commandAliases).sort();

    // Create alias items
    sortedCommands.forEach(commandName => {
        const aliases = commandAliases[commandName];
        if (aliases && aliases.length > 0) {
            const aliasItem = createAliasItem(commandName, aliases);
            aliasList.appendChild(aliasItem);
        }
    });
}

/**
 * Create an alias item element
 * @param {string} commandName - Original command name
 * @param {Array} aliases - Command aliases
 * @returns {HTMLElement} Alias item element
 */
function createAliasItem(commandName, aliases) {
    // Clone the template
    const template = document.getElementById('alias-item-template');
    const aliasItem = template.content.cloneNode(true).querySelector('.alias-item');

    // Set command name
    const nameElement = aliasItem.querySelector('.command-name');
    nameElement.textContent = commandName;

    // Add alias tags
    const aliasTagsList = aliasItem.querySelector('.alias-tags');
    aliases.forEach(alias => {
        const aliasTag = createAliasTag(commandName, alias);
        aliasTagsList.appendChild(aliasTag);
    });

    return aliasItem;
}

/**
 * Create an alias tag element
 * @param {string} commandName - Original command name
 * @param {string} alias - Command alias
 * @returns {HTMLElement} Alias tag element
 */
function createAliasTag(commandName, alias) {
    // Clone the template
    const template = document.getElementById('alias-tag-template');
    const aliasTag = template.content.cloneNode(true).querySelector('.alias-tag');

    // Set alias name
    const nameElement = aliasTag.querySelector('.alias-name');
    nameElement.textContent = alias;

    // Add event listener to remove button
    const removeButton = aliasTag.querySelector('.remove-alias-btn');
    removeButton.addEventListener('click', () => {
        removeAlias(commandName, alias);
    });

    return aliasTag;
}

/**
 * Populate command select for aliases
 * @param {Array} commands - Command names
 */
function populateCommandSelect(commands) {
    const commandSelect = document.getElementById('alias-command-select');
    commandSelect.innerHTML = '<option value="">Select a command</option>';

    // Sort commands alphabetically
    const sortedCommands = commands.sort();

    // Add command options
    sortedCommands.forEach(commandName => {
        const option = document.createElement('option');
        option.value = commandName;
        option.textContent = commandName;
        commandSelect.appendChild(option);
    });
}

/**
 * Add a command alias
 */
async function addAlias() {
    try {
        // Get input values
        const commandSelect = document.getElementById('alias-command-select');
        const aliasInput = document.getElementById('alias-name-input');
        const feedbackElement = document.getElementById('alias-feedback');

        const commandName = commandSelect.value;
        const aliasName = aliasInput.value.trim();

        // Validate inputs
        if (!commandName) {
            feedbackElement.textContent = 'Please select a command';
            feedbackElement.className = 'mt-2 text-danger';
            return;
        }

        if (!aliasName) {
            feedbackElement.textContent = 'Please enter an alias name';
            feedbackElement.className = 'mt-2 text-danger';
            return;
        }

        // Validate alias format
        if (!/^[a-z][a-z0-9_]*$/.test(aliasName) || aliasName.length > 32) {
            feedbackElement.textContent = 'Alias names must be lowercase, start with a letter, and contain only letters, numbers, and underscores (max 32 characters)';
            feedbackElement.className = 'mt-2 text-danger';
            return;
        }

        // Get the current guild ID
        const guildId = window.selectedGuildId; // Use global guild ID
        if (!guildId) {
            feedbackElement.textContent = 'No guild selected';
            feedbackElement.className = 'mt-2 text-danger';
            return;
        }

        // Prepare request data
        const requestData = {
            command_name: commandName,
            alias_name: aliasName
        };

        // Send request to API
        await API.post(`/dashboard/api/guilds/${guildId}/command-customizations/aliases`, requestData); // Updated endpoint

        // Clear input
        aliasInput.value = '';

        // Show success message
        feedbackElement.textContent = 'Alias added successfully';
        feedbackElement.className = 'mt-2 text-success';

        // Reload command customizations
        loadCommandCustomizationData(guildId); // Reload data for the current guild

        Toast.success('Command alias added successfully');
    } catch (error) {
        console.error('Error adding command alias:', error);

        const feedbackElement = document.getElementById('alias-feedback');
        feedbackElement.textContent = `Failed to add command alias: ${error.message || error}`;
        feedbackElement.className = 'mt-2 text-danger';

        Toast.error('Failed to add command alias');
    }
}

/**
 * Remove a command alias
 * @param {string} commandName - Original command name
 * @param {string} aliasName - Command alias
 */
async function removeAlias(commandName, aliasName) {
    try {
        // Get the current guild ID
        const guildId = window.selectedGuildId; // Use global guild ID
        if (!guildId) {
            Toast.error('No guild selected');
            return;
        }

        // Prepare request data
        const requestData = {
            command_name: commandName,
            alias_name: aliasName
        };

        // Send request to API
        await API.delete(`/dashboard/api/guilds/${guildId}/command-customizations/aliases`, requestData); // Updated endpoint

        // Reload command customizations
        loadCommandCustomizationData(guildId); // Reload data for the current guild

        Toast.success('Command alias removed successfully');
    } catch (error) {
        console.error('Error removing command alias:', error);
        Toast.error(`Failed to remove command alias: ${error.message || error}`);
    }
}

/**
 * Sync commands to Discord
 */
async function syncCommands() {
    try {
        // Get the current guild ID
        const guildId = window.selectedGuildId; // Use global guild ID
        if (!guildId) {
            Toast.error('No guild selected');
            return;
        }

        // Show feedback
        const feedbackElement = document.getElementById('sync-feedback');
        feedbackElement.textContent = 'Syncing commands...';
        feedbackElement.className = 'mt-2 text-info';

        // Send request to API
        await API.post(`/dashboard/api/guilds/${guildId}/sync-commands`); // Updated endpoint

        // Show success message
        feedbackElement.textContent = 'Commands synced successfully';
        feedbackElement.className = 'mt-2 text-success';

        Toast.success('Commands synced successfully');
    } catch (error) {
        console.error('Error syncing commands:', error);

        // Show error message
        const feedbackElement = document.getElementById('sync-feedback');
        feedbackElement.textContent = `Failed to sync commands: ${error.message || error}`;
        feedbackElement.className = 'mt-2 text-danger';

        Toast.error('Failed to sync commands');
    }
}

/**
 * Filter commands by search query
 */
function filterCommands() {
    const searchQuery = document.getElementById('command-search').value.toLowerCase();
    const commandItems = document.querySelectorAll('#command-list .command-item');

    commandItems.forEach(item => {
        const commandName = item.dataset.commandName;
        if (commandName.includes(searchQuery)) {
            item.style.display = 'block';
        } else {
            item.style.display = 'none';
        }
    });
}
