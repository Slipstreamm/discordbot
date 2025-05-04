/**
 * Main JavaScript file for the Discord Bot Dashboard
 */

// Initialize components when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  // Initialize modals
  Modal.init();

  // Initialize sidebar toggle
  initSidebar();

  // Initialize authentication
  initAuth();

  // Initialize tabs
  initTabs();

  // Initialize dropdowns
  initDropdowns();
});

/**
 * Initialize sidebar functionality
 */
function initSidebar() {
  const sidebarToggle = document.getElementById('sidebar-toggle');
  const sidebar = document.getElementById('sidebar');

  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', () => {
      sidebar.classList.toggle('show');
    });

    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', (event) => {
      if (window.innerWidth <= 768 &&
          sidebar.classList.contains('show') &&
          !sidebar.contains(event.target) &&
          event.target !== sidebarToggle) {
        sidebar.classList.remove('show');
      }
    });
  }

  // Set active nav item based on current page
  const currentPath = window.location.pathname;
  document.querySelectorAll('.nav-item').forEach(item => {
    const href = item.getAttribute('href');
    if (href && currentPath.includes(href)) {
      item.classList.add('active');
    }

    // Add click event to nav items
    item.addEventListener('click', (event) => {
      // Prevent default only if it's a section link
      if (href && href.startsWith('#')) {
        event.preventDefault();

        // Remove active class from all nav items
        document.querySelectorAll('.nav-item').forEach(navItem => {
          navItem.classList.remove('active');
        });

        // Add active class to clicked item
        item.classList.add('active');

        // Hide all sections
        document.querySelectorAll('.dashboard-section').forEach(section => {
          section.style.display = 'none';
        });

        // Show the target section
        const sectionId = item.getAttribute('data-section');
        if (sectionId) {
          const section = document.getElementById(sectionId);
          if (section) {
            section.style.display = 'block';
          }
        }

        // Close sidebar on mobile
        if (window.innerWidth <= 768 && sidebar) {
          sidebar.classList.remove('show');
        }
      }
    });
  });
}

/**
 * Initialize authentication
 */
function initAuth() {
  const loginButton = document.getElementById('login-button');
  const logoutButton = document.getElementById('logout-button');
  const authSection = document.getElementById('auth-section');
  const dashboardSection = document.getElementById('dashboard-container');

  // Check authentication status
  checkAuthStatus();

  // Login button event
  if (loginButton) {
    loginButton.addEventListener('click', () => {
      // Show loading state
      loginButton.disabled = true;
      loginButton.classList.add('btn-loading');

      // Redirect to login page
      window.location.href = '/dashboard/api/auth/login';
    });
  }

  // Logout button event
  if (logoutButton) {
    logoutButton.addEventListener('click', () => {
      // Show loading state
      logoutButton.disabled = true;
      logoutButton.classList.add('btn-loading');

      // Clear session
      fetch('/dashboard/api/auth/logout', {
        method: 'POST',
        credentials: 'same-origin' // Important for cookies
      })
        .then(() => {
          // Redirect to login page
          Toast.success('Logged out successfully');
          setTimeout(() => {
            window.location.reload();
          }, 1000);
        })
        .catch(error => {
          console.error('Logout error:', error);
          Toast.error('Failed to logout. Please try again.');
          logoutButton.disabled = false;
          logoutButton.classList.remove('btn-loading');
        });
    });
  }

  /**
   * Check if user is authenticated
   */
  function checkAuthStatus() {
    // Show loading indicator
    const loadingContainer = document.createElement('div');
    loadingContainer.className = 'loading-container';
    loadingContainer.innerHTML = '<div class="loading-spinner"></div>';
    loadingContainer.style.position = 'fixed';
    loadingContainer.style.top = '50%';
    loadingContainer.style.left = '50%';
    loadingContainer.style.transform = 'translate(-50%, -50%)';
    document.body.appendChild(loadingContainer);

    fetch('/dashboard/api/auth/status', {
      credentials: 'same-origin' // Important for cookies
    })
      .then(response => {
        if (!response.ok) {
          throw new Error(`Status check failed: ${response.status}`);
        }
        return response.json();
      })
      .then(data => {
        console.log('Auth status:', data);

        if (data.authenticated) {
          // User is authenticated, show dashboard
          if (authSection) authSection.style.display = 'none';
          if (dashboardSection) dashboardSection.style.display = 'block';

          // If user data is included in the response, use it
          if (data.user) {
            updateUserDisplay(data.user);
          } else {
            // Otherwise load user info separately
            loadUserInfo();
          }

          // Load initial data
          loadDashboardData();
        } else {
          // User is not authenticated, show login
          if (authSection) authSection.style.display = 'block';
          if (dashboardSection) dashboardSection.style.display = 'none';

          // Show message if provided
          if (data.message) {
            console.log('Auth message:', data.message);
          }
        }
      })
      .catch(error => {
        console.error('Auth check error:', error);
        // Assume not authenticated on error
        if (authSection) authSection.style.display = 'block';
        if (dashboardSection) dashboardSection.style.display = 'none';

        // Show error toast
        Toast.error('Failed to check authentication status. Please try again.');
      })
      .finally(() => {
        // Remove loading indicator
        document.body.removeChild(loadingContainer);
      });
  }

  /**
   * Load user information
   */
  function loadUserInfo() {
    fetch('/dashboard/api/auth/user', {
      credentials: 'same-origin' // Important for cookies
    })
      .then(response => {
        if (!response.ok) {
          if (response.status === 401) {
            // User is not authenticated, show login
            if (authSection) authSection.style.display = 'block';
            if (dashboardSection) dashboardSection.style.display = 'none';
            throw new Error('Not authenticated');
          }
          throw new Error(`Failed to load user info: ${response.status}`);
        }
        return response.json();
      })
      .then(user => {
        updateUserDisplay(user);
      })
      .catch(error => {
        console.error('Error loading user info:', error);
        if (error.message !== 'Not authenticated') {
          Toast.error('Failed to load user information');
        }
      });
  }

  /**
   * Update user display with user data
   * @param {Object} user - User data object
   */
  function updateUserDisplay(user) {
    // Update username display
    const usernameSpan = document.getElementById('username');
    if (usernameSpan) {
      usernameSpan.textContent = user.username;
    }

    // Update avatar if available
    const userAvatar = document.getElementById('user-avatar');
    if (userAvatar) {
      if (user.avatar) {
        userAvatar.style.backgroundImage = `url(https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png)`;
        userAvatar.textContent = '';
      } else {
        // Set initials as fallback
        userAvatar.textContent = user.username.substring(0, 1).toUpperCase();
      }
    }
  }
}

/**
 * Initialize tab functionality
 */
function initTabs() {
  document.querySelectorAll('.tabs').forEach(tabContainer => {
    const tabs = tabContainer.querySelectorAll('.tab');

    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        // Get target content ID
        const target = tab.getAttribute('data-target');
        if (!target) return;

        // Remove active class from all tabs
        tabs.forEach(t => t.classList.remove('active'));

        // Add active class to clicked tab
        tab.classList.add('active');

        // Hide all tab content
        const tabContents = document.querySelectorAll('.tab-content');
        tabContents.forEach(content => {
          content.classList.remove('active');
        });

        // Show target content
        const targetContent = document.getElementById(target);
        if (targetContent) {
          targetContent.classList.add('active');
        }
      });
    });
  });
}

/**
 * Initialize dropdown functionality
 */
function initDropdowns() {
  document.querySelectorAll('.dropdown-toggle').forEach(toggle => {
    toggle.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();

      const dropdown = toggle.closest('.dropdown');
      const menu = dropdown.querySelector('.dropdown-menu');

      // Close all other dropdowns
      document.querySelectorAll('.dropdown-menu.show').forEach(openMenu => {
        if (openMenu !== menu) {
          openMenu.classList.remove('show');
        }
      });

      // Toggle this dropdown
      menu.classList.toggle('show');
    });
  });

  // Close dropdowns when clicking outside
  document.addEventListener('click', (event) => {
    if (!event.target.closest('.dropdown')) {
      document.querySelectorAll('.dropdown-menu.show').forEach(menu => {
        menu.classList.remove('show');
      });
    }
  });
}

/**
 * Load dashboard data
 */
function loadDashboardData() {
  // Load guilds for server select
  loadGuilds();

  // Load global settings
  loadGlobalSettings();
}

/**
 * Show a global error message about missing bot token
 */
function showBotTokenMissingError() {
  // Create error banner
  const errorBanner = document.createElement('div');
  errorBanner.className = 'error-message';
  errorBanner.style.margin = '0';
  errorBanner.style.borderRadius = '0';
  errorBanner.style.position = 'sticky';
  errorBanner.style.top = '0';
  errorBanner.style.zIndex = '1000';

  errorBanner.innerHTML = `
    <div style="display: flex; align-items: center; justify-content: space-between;">
      <div>
        <strong>Configuration Error:</strong> Discord Bot Token is not configured.
        <p>Some features like channel selection, role management, and command permissions will not work.</p>
        <p>Please set the <code>DISCORD_BOT_TOKEN</code> environment variable in your .env file.</p>
      </div>
      <button class="btn btn-sm" id="close-error-banner" style="background: transparent; border: none;">×</button>
    </div>
  `;

  // Add to the top of the page
  document.body.insertBefore(errorBanner, document.body.firstChild);

  // Add close button functionality
  document.getElementById('close-error-banner').addEventListener('click', () => {
    errorBanner.remove();
  });
}

/**
 * Load guilds for server select dropdown
 */
function loadGuilds() {
  const guildSelect = document.getElementById('guild-select');
  if (!guildSelect) return;

  // Show loading state
  guildSelect.disabled = true;
  guildSelect.innerHTML = '<option value="">Loading servers...</option>';

  // Fetch guilds from API
  API.get('/dashboard/api/guilds')
    .then(guilds => {
      // Clear loading state
      guildSelect.innerHTML = '<option value="">--Please choose a server--</option>';

      // Add guilds to select
      guilds.forEach(guild => {
        const option = document.createElement('option');
        option.value = guild.id;
        option.textContent = guild.name;
        guildSelect.appendChild(option);
      });

      // Enable select
      guildSelect.disabled = false;

      // Add change event
      guildSelect.addEventListener('change', () => {
        const guildId = guildSelect.value;
        if (guildId) {
          loadGuildSettings(guildId);
        } else {
          // Hide settings form if no guild selected
          const settingsForm = document.getElementById('settings-form');
          if (settingsForm) {
            settingsForm.style.display = 'none';
          }
        }
      });
    })
    .catch(error => {
      console.error('Error loading guilds:', error);
      guildSelect.innerHTML = '<option value="">Error loading servers</option>';
      guildSelect.disabled = false;
      Toast.error('Failed to load servers. Please try again.');
    });
}

/**
 * Load settings for a specific guild
 * @param {string} guildId - The guild ID
 */
function loadGuildSettings(guildId) {
  const settingsForm = document.getElementById('settings-form');
  if (!settingsForm) return;

  // Show loading state
  const loadingContainer = document.createElement('div');
  loadingContainer.className = 'loading-container';
  loadingContainer.innerHTML = '<div class="loading-spinner"></div><p>Loading server settings...</p>';
  loadingContainer.style.textAlign = 'center';
  loadingContainer.style.padding = '2rem';

  settingsForm.style.display = 'none';
  settingsForm.parentNode.insertBefore(loadingContainer, settingsForm);

  // Fetch guild settings from API
  API.get(`/dashboard/api/guilds/${guildId}/settings`)
    .then(settings => {
      // Remove loading container
      loadingContainer.remove();

      // Show settings form
      settingsForm.style.display = 'block';

      // Populate form with settings
      populateGuildSettings(settings);

      // Load additional data
      loadGuildChannels(guildId);
      loadGuildRoles(guildId);
      loadGuildCommands(guildId);
    })
    .catch(error => {
      console.error('Error loading guild settings:', error);
      loadingContainer.innerHTML = '<p class="text-danger">Error loading server settings. Please try again.</p>';
      Toast.error('Failed to load server settings. Please try again.');
    });
}

/**
 * Populate guild settings form with data
 * @param {Object} settings - The guild settings
 */
function populateGuildSettings(settings) {
  // Prefix
  const prefixInput = document.getElementById('prefix-input');
  if (prefixInput) {
    prefixInput.value = settings.prefix || '!';
  }

  // Welcome settings
  const welcomeChannel = document.getElementById('welcome-channel');
  const welcomeMessage = document.getElementById('welcome-message');

  if (welcomeChannel && welcomeMessage) {
    welcomeChannel.value = settings.welcome_channel_id || '';
    welcomeMessage.value = settings.welcome_message || '';
  }

  // Goodbye settings
  const goodbyeChannel = document.getElementById('goodbye-channel');
  const goodbyeMessage = document.getElementById('goodbye-message');

  if (goodbyeChannel && goodbyeMessage) {
    goodbyeChannel.value = settings.goodbye_channel_id || '';
    goodbyeMessage.value = settings.goodbye_message || '';
  }

  // Cogs (modules)
  const cogsList = document.getElementById('cogs-list');
  if (cogsList && settings.enabled_cogs) {
    cogsList.innerHTML = '';

    Object.entries(settings.enabled_cogs).forEach(([cogName, enabled]) => {
      const cogDiv = document.createElement('div');

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.id = `cog-${cogName}`;
      checkbox.name = `cog-${cogName}`;
      checkbox.checked = enabled;

      const label = document.createElement('label');
      label.htmlFor = `cog-${cogName}`;
      label.textContent = cogName;

      cogDiv.appendChild(checkbox);
      cogDiv.appendChild(label);
      cogsList.appendChild(cogDiv);
    });
  }
}

/**
 * Load channels for a guild
 * @param {string} guildId - The guild ID
 */
function loadGuildChannels(guildId) {
  const welcomeChannelSelect = document.getElementById('welcome-channel-select');
  const goodbyeChannelSelect = document.getElementById('goodbye-channel-select');

  if (!welcomeChannelSelect && !goodbyeChannelSelect) return;

  // Fetch channels from API
  API.get(`/dashboard/api/guilds/${guildId}/channels`)
    .then(channels => {
      // Filter text channels
      const textChannels = channels.filter(channel => channel.type === 0);

      // Populate welcome channel select
      if (welcomeChannelSelect) {
        welcomeChannelSelect.innerHTML = '<option value="">-- Select Channel --</option>';

        textChannels.forEach(channel => {
          const option = document.createElement('option');
          option.value = channel.id;
          option.textContent = `#${channel.name}`;
          welcomeChannelSelect.appendChild(option);
        });

        // Set current value if available
        const welcomeChannelInput = document.getElementById('welcome-channel');
        if (welcomeChannelInput && welcomeChannelInput.value) {
          welcomeChannelSelect.value = welcomeChannelInput.value;
        }

        // Add change event
        welcomeChannelSelect.addEventListener('change', () => {
          if (welcomeChannelInput) {
            welcomeChannelInput.value = welcomeChannelSelect.value;
          }
        });
      }

      // Populate goodbye channel select
      if (goodbyeChannelSelect) {
        goodbyeChannelSelect.innerHTML = '<option value="">-- Select Channel --</option>';

        textChannels.forEach(channel => {
          const option = document.createElement('option');
          option.value = channel.id;
          option.textContent = `#${channel.name}`;
          goodbyeChannelSelect.appendChild(option);
        });

        // Set current value if available
        const goodbyeChannelInput = document.getElementById('goodbye-channel');
        if (goodbyeChannelInput && goodbyeChannelInput.value) {
          goodbyeChannelSelect.value = goodbyeChannelInput.value;
        }

        // Add change event
        goodbyeChannelSelect.addEventListener('change', () => {
          if (goodbyeChannelInput) {
            goodbyeChannelInput.value = goodbyeChannelSelect.value;
          }
        });
      }
    })
    .catch(error => {
      console.error('Error loading channels:', error);

      // Check for specific error about missing bot token
      if (error.status === 503 && error.message && error.message.includes('Bot token not configured')) {
        // Show global error banner
        showBotTokenMissingError();

        // Show a more helpful message in the channel selects
        if (welcomeChannelSelect) {
          welcomeChannelSelect.innerHTML = '<option value="">Bot token not configured</option>';
          welcomeChannelSelect.disabled = true;
        }
        if (goodbyeChannelSelect) {
          goodbyeChannelSelect.innerHTML = '<option value="">Bot token not configured</option>';
          goodbyeChannelSelect.disabled = true;
        }

        // Add a visible error message
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.innerHTML = `
          <p>The Discord bot token is not configured. Channel selection is unavailable.</p>
          <p>Please set the <code>DISCORD_BOT_TOKEN</code> environment variable in your .env file.</p>
        `;

        // Add the error message near the channel selects
        if (welcomeChannelSelect && welcomeChannelSelect.parentNode) {
          welcomeChannelSelect.parentNode.appendChild(errorDiv);
        }
      } else {
        Toast.error('Failed to load channels. Please try again.');
      }
    });
}

/**
 * Load roles for a guild
 * @param {string} guildId - The guild ID
 */
function loadGuildRoles(guildId) {
  const roleSelect = document.getElementById('role-select');
  if (!roleSelect) return;

  // Fetch roles from API
  API.get(`/dashboard/api/guilds/${guildId}/roles`)
    .then(roles => {
      roleSelect.innerHTML = '<option value="">-- Select Role --</option>';

      roles.forEach(role => {
        const option = document.createElement('option');
        option.value = role.id;
        option.textContent = role.name;

        // Set color if available
        if (role.color) {
          option.style.color = `#${role.color.toString(16).padStart(6, '0')}`;
        }

        roleSelect.appendChild(option);
      });
    })
    .catch(error => {
      console.error('Error loading roles:', error);

      // Check for specific error about missing bot token
      if (error.status === 503 && error.message && error.message.includes('Bot token not configured')) {
        // Show global error banner (if not already shown)
        showBotTokenMissingError();

        // Show a more helpful message in the role select
        roleSelect.innerHTML = '<option value="">Bot token not configured</option>';
        roleSelect.disabled = true;

        // Add a visible error message
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.innerHTML = `
          <p>The Discord bot token is not configured. Role selection is unavailable.</p>
          <p>Please set the <code>DISCORD_BOT_TOKEN</code> environment variable in your .env file.</p>
        `;

        // Add the error message near the role select
        if (roleSelect.parentNode) {
          roleSelect.parentNode.appendChild(errorDiv);
        }
      } else {
        Toast.error('Failed to load roles. Please try again.');
      }
    });
}

/**
 * Load commands for a guild
 * @param {string} guildId - The guild ID
 */
function loadGuildCommands(guildId) {
  const commandSelect = document.getElementById('command-select');
  if (!commandSelect) return;

  // Fetch commands from API
  API.get(`/dashboard/api/guilds/${guildId}/commands`)
    .then(commands => {
      commandSelect.innerHTML = '<option value="">-- Select Command --</option>';

      commands.forEach(command => {
        const option = document.createElement('option');
        option.value = command.name;
        option.textContent = command.name;

        // Add description as title attribute
        if (command.description) {
          option.title = command.description;
        }

        commandSelect.appendChild(option);
      });

      // Load command permissions
      loadCommandPermissions(guildId);
    })
    .catch(error => {
      console.error('Error loading commands:', error);

      // Check for specific error about missing bot token
      if (error.status === 503 && error.message && error.message.includes('Bot token not configured')) {
        // Show global error banner (if not already shown)
        showBotTokenMissingError();

        // Show a more helpful message in the command select
        commandSelect.innerHTML = '<option value="">Bot token not configured</option>';
        commandSelect.disabled = true;

        // Add a visible error message
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.innerHTML = `
          <p>The Discord bot token is not configured. Command selection is unavailable.</p>
          <p>Please set the <code>DISCORD_BOT_TOKEN</code> environment variable in your .env file.</p>
        `;

        // Add the error message near the command select
        if (commandSelect.parentNode) {
          commandSelect.parentNode.appendChild(errorDiv);
        }
      } else {
        Toast.error('Failed to load commands. Please try again.');
      }
    });
}

/**
 * Load command permissions for a guild
 * @param {string} guildId - The guild ID
 */
function loadCommandPermissions(guildId) {
  const currentPerms = document.getElementById('current-perms');
  if (!currentPerms) return;

  // Show loading state
  currentPerms.innerHTML = '<div class="loading-spinner-container"><div class="loading-spinner loading-spinner-sm"></div></div>';

  // Fetch command permissions from API
  API.get(`/dashboard/api/guilds/${guildId}/command-permissions`)
    .then(permissions => {
      // Clear loading state
      currentPerms.innerHTML = '';

      if (permissions.length === 0) {
        currentPerms.innerHTML = '<div class="text-gray">No custom permissions set.</div>';
        return;
      }

      // Group permissions by command
      const permsByCommand = {};

      permissions.forEach(perm => {
        if (!permsByCommand[perm.command]) {
          permsByCommand[perm.command] = [];
        }

        permsByCommand[perm.command].push(perm);
      });

      // Create permission elements
      Object.entries(permsByCommand).forEach(([command, perms]) => {
        const commandDiv = document.createElement('div');
        commandDiv.className = 'command-perms';
        commandDiv.innerHTML = `<div class="command-name">${command}</div>`;

        const rolesList = document.createElement('div');
        rolesList.className = 'roles-list';

        perms.forEach(perm => {
          const roleSpan = document.createElement('span');
          roleSpan.className = 'role-badge';
          roleSpan.textContent = perm.role_name;
          roleSpan.dataset.roleId = perm.role_id;
          roleSpan.dataset.command = command;

          // Add remove button
          const removeBtn = document.createElement('button');
          removeBtn.className = 'role-remove';
          removeBtn.innerHTML = '&times;';
          removeBtn.addEventListener('click', () => {
            removeCommandPermission(guildId, command, perm.role_id);
          });

          roleSpan.appendChild(removeBtn);
          rolesList.appendChild(roleSpan);
        });

        commandDiv.appendChild(rolesList);
        currentPerms.appendChild(commandDiv);
      });
    })
    .catch(error => {
      console.error('Error loading command permissions:', error);
      currentPerms.innerHTML = '<div class="text-danger">Error loading permissions.</div>';
    });
}

/**
 * Add a command permission
 * @param {string} guildId - The guild ID
 * @param {string} command - The command name
 * @param {string} roleId - The role ID
 */
function addCommandPermission(guildId, command, roleId) {
  const addPermButton = document.getElementById('add-perm-button');
  const permsFeedback = document.getElementById('perms-feedback');

  if (!command || !roleId) {
    permsFeedback.textContent = 'Please select both a command and a role.';
    permsFeedback.className = 'error';
    return;
  }

  // Show loading state
  addPermButton.disabled = true;
  addPermButton.classList.add('btn-loading');

  // Send request to API
  API.post(`/dashboard/api/guilds/${guildId}/command-permissions`, {
    command,
    role_id: roleId
  })
    .then(() => {
      // Show success message
      permsFeedback.textContent = 'Permission added successfully.';
      permsFeedback.className = '';

      // Reload permissions
      loadCommandPermissions(guildId);

      // Reset form
      document.getElementById('command-select').value = '';
      document.getElementById('role-select').value = '';
    })
    .catch(error => {
      console.error('Error adding permission:', error);
      permsFeedback.textContent = 'Error adding permission. Please try again.';
      permsFeedback.className = 'error';
    })
    .finally(() => {
      // Remove loading state
      addPermButton.disabled = false;
      addPermButton.classList.remove('btn-loading');
    });
}

/**
 * Remove a command permission
 * @param {string} guildId - The guild ID
 * @param {string} command - The command name
 * @param {string} roleId - The role ID
 */
function removeCommandPermission(guildId, command, roleId) {
  // Send request to API
  API.delete(`/dashboard/api/guilds/${guildId}/command-permissions?command=${command}&role_id=${roleId}`)
    .then(() => {
      // Show success message
      Toast.success('Permission removed successfully.');

      // Reload permissions
      loadCommandPermissions(guildId);
    })
    .catch(error => {
      console.error('Error removing permission:', error);
      Toast.error('Error removing permission. Please try again.');
    });
}

/**
 * Load global AI settings
 */
function loadGlobalSettings() {
  const aiSettingsSection = document.getElementById('ai-settings-section');
  if (!aiSettingsSection) return;

  // Show loading state
  const loadingContainer = document.createElement('div');
  loadingContainer.className = 'loading-container';
  loadingContainer.innerHTML = '<div class="loading-spinner"></div><p>Loading AI settings...</p>';
  loadingContainer.style.textAlign = 'center';
  loadingContainer.style.padding = '2rem';

  aiSettingsSection.prepend(loadingContainer);

  // Fetch global settings from API
  API.get('/dashboard/api/settings')
    .then(settings => {
      // Remove loading container
      loadingContainer.remove();

      console.log('Loaded AI settings:', settings);

      // Populate AI model select
      const modelSelect = document.getElementById('ai-model-select');
      if (modelSelect && settings.model) {
        modelSelect.value = settings.model;
      }

      // Populate temperature slider
      const temperatureSlider = document.getElementById('ai-temperature');
      const temperatureValue = document.getElementById('temperature-value');
      if (temperatureSlider && temperatureValue) {
        const temp = settings.temperature !== undefined ? settings.temperature : 0.7;
        temperatureSlider.value = temp;
        temperatureValue.textContent = temp;

        // Add input event for live update
        temperatureSlider.addEventListener('input', () => {
          temperatureValue.textContent = temperatureSlider.value;
        });
      }

      // Populate max tokens
      const maxTokensInput = document.getElementById('ai-max-tokens');
      if (maxTokensInput) {
        const maxTokens = settings.max_tokens !== undefined ? settings.max_tokens : 1000;
        maxTokensInput.value = maxTokens;
      }

      // Populate character settings
      const characterInput = document.getElementById('ai-character');
      const characterInfoInput = document.getElementById('ai-character-info');

      if (characterInput) {
        characterInput.value = settings.character || '';
      }

      if (characterInfoInput) {
        characterInfoInput.value = settings.character_info || '';
      }

      // Populate system prompt
      const systemPromptInput = document.getElementById('ai-system-prompt');
      if (systemPromptInput) {
        systemPromptInput.value = settings.system_message || '';
      }

      // Populate custom instructions
      const customInstructionsInput = document.getElementById('ai-custom-instructions');
      if (customInstructionsInput) {
        customInstructionsInput.value = settings.custom_instructions || '';
      }

      // Set up save buttons
      setupAISettingsSaveButtons(settings);
    })
    .catch(error => {
      console.error('Error loading global settings:', error);
      loadingContainer.innerHTML = '<p class="text-danger">Error loading AI settings. Please try again.</p>';
      Toast.error('Failed to load AI settings. Please try again.');
    });
}

/**
 * Set up AI settings save buttons
 * @param {Object} initialSettings - The initial settings
 */
function setupAISettingsSaveButtons(initialSettings) {
  // AI Settings save button
  const saveAISettingsButton = document.getElementById('save-ai-settings-button');
  if (saveAISettingsButton) {
    saveAISettingsButton.addEventListener('click', () => {
      const modelSelect = document.getElementById('ai-model-select');
      const temperatureSlider = document.getElementById('ai-temperature');
      const maxTokensInput = document.getElementById('ai-max-tokens');
      const reasoningEnabled = document.getElementById('ai-reasoning-enabled');
      const reasoningEffort = document.getElementById('ai-reasoning-effort');
      const webSearchEnabled = document.getElementById('ai-web-search-enabled');

      // Create settings object
      const settings = {
        ...initialSettings, // Keep other settings
        model: modelSelect ? modelSelect.value : initialSettings.model,
        temperature: temperatureSlider ? parseFloat(temperatureSlider.value) : initialSettings.temperature,
        max_tokens: maxTokensInput ? parseInt(maxTokensInput.value) : initialSettings.max_tokens
      };

      // Add optional settings if they exist
      if (reasoningEnabled) {
        settings.reasoning_enabled = reasoningEnabled.checked;
      }

      if (reasoningEffort) {
        settings.reasoning_effort = reasoningEffort.value;
      }

      if (webSearchEnabled) {
        settings.web_search_enabled = webSearchEnabled.checked;
      }

      // Save settings
      saveSettings(settings, saveAISettingsButton, 'AI settings saved successfully');
    });
  }

  // Character settings save button
  const saveCharacterSettingsButton = document.getElementById('save-character-settings-button');
  if (saveCharacterSettingsButton) {
    saveCharacterSettingsButton.addEventListener('click', () => {
      const characterInput = document.getElementById('ai-character');
      const characterInfoInput = document.getElementById('ai-character-info');
      const characterBreakdown = document.getElementById('ai-character-breakdown');

      // Create settings object
      const settings = {
        ...initialSettings, // Keep other settings
        character: characterInput ? characterInput.value : initialSettings.character,
        character_info: characterInfoInput ? characterInfoInput.value : initialSettings.character_info
      };

      // Add optional settings if they exist
      if (characterBreakdown) {
        settings.character_breakdown = characterBreakdown.checked;
      }

      // Save settings
      saveSettings(settings, saveCharacterSettingsButton, 'Character settings saved successfully');
    });
  }

  // System prompt save button
  const saveSystemPromptButton = document.getElementById('save-system-prompt-button');
  if (saveSystemPromptButton) {
    saveSystemPromptButton.addEventListener('click', () => {
      const systemPromptInput = document.getElementById('ai-system-prompt');

      // Create settings object
      const settings = {
        ...initialSettings, // Keep other settings
        system_message: systemPromptInput ? systemPromptInput.value : initialSettings.system_message
      };

      // Save settings
      saveSettings(settings, saveSystemPromptButton, 'System prompt saved successfully');
    });
  }

  // Custom instructions save button
  const saveCustomInstructionsButton = document.getElementById('save-custom-instructions-button');
  if (saveCustomInstructionsButton) {
    saveCustomInstructionsButton.addEventListener('click', () => {
      const customInstructionsInput = document.getElementById('ai-custom-instructions');

      // Create settings object
      const settings = {
        ...initialSettings, // Keep other settings
        custom_instructions: customInstructionsInput ? customInstructionsInput.value : initialSettings.custom_instructions
      };

      // Save settings
      saveSettings(settings, saveCustomInstructionsButton, 'Custom instructions saved successfully');
    });
  }

  // Clear buttons
  const clearCharacterSettingsButton = document.getElementById('clear-character-settings-button');
  if (clearCharacterSettingsButton) {
    clearCharacterSettingsButton.addEventListener('click', () => {
      const characterInput = document.getElementById('ai-character');
      const characterInfoInput = document.getElementById('ai-character-info');

      if (characterInput) characterInput.value = '';
      if (characterInfoInput) characterInfoInput.value = '';

      // Create settings object
      const settings = {
        ...initialSettings, // Keep other settings
        character: '',
        character_info: ''
      };

      // Save settings
      saveSettings(settings, clearCharacterSettingsButton, 'Character settings cleared');
    });
  }

  const clearCustomInstructionsButton = document.getElementById('clear-custom-instructions-button');
  if (clearCustomInstructionsButton) {
    clearCustomInstructionsButton.addEventListener('click', () => {
      const customInstructionsInput = document.getElementById('ai-custom-instructions');

      if (customInstructionsInput) customInstructionsInput.value = '';

      // Create settings object
      const settings = {
        ...initialSettings, // Keep other settings
        custom_instructions: ''
      };

      // Save settings
      saveSettings(settings, clearCustomInstructionsButton, 'Custom instructions cleared');
    });
  }

  // Reset buttons
  const resetAISettingsButton = document.getElementById('reset-ai-settings-button');
  if (resetAISettingsButton) {
    resetAISettingsButton.addEventListener('click', () => {
      const modelSelect = document.getElementById('ai-model-select');
      const temperatureSlider = document.getElementById('ai-temperature');
      const temperatureValue = document.getElementById('temperature-value');
      const maxTokensInput = document.getElementById('ai-max-tokens');

      if (modelSelect) modelSelect.value = 'openai/gpt-3.5-turbo';
      if (temperatureSlider) temperatureSlider.value = 0.7;
      if (temperatureValue) temperatureValue.textContent = 0.7;
      if (maxTokensInput) maxTokensInput.value = 1000;

      // Create settings object
      const settings = {
        ...initialSettings, // Keep other settings
        model: 'openai/gpt-3.5-turbo',
        temperature: 0.7,
        max_tokens: 1000
      };

      // Save settings
      saveSettings(settings, resetAISettingsButton, 'AI settings reset to defaults');
    });
  }

  const resetSystemPromptButton = document.getElementById('reset-system-prompt-button');
  if (resetSystemPromptButton) {
    resetSystemPromptButton.addEventListener('click', () => {
      const systemPromptInput = document.getElementById('ai-system-prompt');

      if (systemPromptInput) systemPromptInput.value = '';

      // Create settings object
      const settings = {
        ...initialSettings, // Keep other settings
        system_message: ''
      };

      // Save settings
      saveSettings(settings, resetSystemPromptButton, 'System prompt reset to default');
    });
  }
}

/**
 * Save settings to the API
 * @param {Object} settings - The settings to save
 * @param {HTMLElement} button - The button that triggered the save
 * @param {string} successMessage - The message to show on success
 */
function saveSettings(settings, button, successMessage) {
  // Save settings to API
  API.post('/dashboard/api/settings', { settings }, button)
    .then(response => {
      console.log('Settings saved:', response);
      Toast.success(successMessage);
    })
    .catch(error => {
      console.error('Error saving settings:', error);
      Toast.error('Failed to save settings. Please try again.');
    });
}
