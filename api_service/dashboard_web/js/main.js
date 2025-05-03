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
      window.location.href = '/dashboard/api/auth/login';
    });
  }
  
  // Logout button event
  if (logoutButton) {
    logoutButton.addEventListener('click', () => {
      // Clear session
      fetch('/dashboard/api/auth/logout', { method: 'POST' })
        .then(() => {
          // Redirect to login page
          window.location.reload();
        })
        .catch(error => {
          console.error('Logout error:', error);
          Toast.error('Failed to logout. Please try again.');
        });
    });
  }
  
  /**
   * Check if user is authenticated
   */
  function checkAuthStatus() {
    fetch('/dashboard/api/auth/status')
      .then(response => response.json())
      .then(data => {
        if (data.authenticated) {
          // User is authenticated, show dashboard
          if (authSection) authSection.style.display = 'none';
          if (dashboardSection) dashboardSection.style.display = 'block';
          
          // Load user info
          loadUserInfo();
          
          // Load initial data
          loadDashboardData();
        } else {
          // User is not authenticated, show login
          if (authSection) authSection.style.display = 'block';
          if (dashboardSection) dashboardSection.style.display = 'none';
        }
      })
      .catch(error => {
        console.error('Auth check error:', error);
        // Assume not authenticated on error
        if (authSection) authSection.style.display = 'block';
        if (dashboardSection) dashboardSection.style.display = 'none';
      });
  }
  
  /**
   * Load user information
   */
  function loadUserInfo() {
    fetch('/dashboard/api/auth/user')
      .then(response => response.json())
      .then(user => {
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
      })
      .catch(error => {
        console.error('Error loading user info:', error);
      });
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
      Toast.error('Failed to load channels. Please try again.');
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
      Toast.error('Failed to load roles. Please try again.');
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
      Toast.error('Failed to load commands. Please try again.');
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
  
  // Fetch global settings from API
  API.get('/dashboard/api/settings')
    .then(settings => {
      // Populate AI model select
      const modelSelect = document.getElementById('ai-model-select');
      if (modelSelect && settings.model) {
        modelSelect.value = settings.model;
      }
      
      // Populate temperature slider
      const temperatureSlider = document.getElementById('ai-temperature');
      const temperatureValue = document.getElementById('temperature-value');
      if (temperatureSlider && temperatureValue && settings.temperature) {
        temperatureSlider.value = settings.temperature;
        temperatureValue.textContent = settings.temperature;
        
        // Add input event for live update
        temperatureSlider.addEventListener('input', () => {
          temperatureValue.textContent = temperatureSlider.value;
        });
      }
      
      // Populate max tokens
      const maxTokensInput = document.getElementById('ai-max-tokens');
      if (maxTokensInput && settings.max_tokens) {
        maxTokensInput.value = settings.max_tokens;
      }
      
      // Populate character settings
      const characterInput = document.getElementById('ai-character');
      const characterInfoInput = document.getElementById('ai-character-info');
      
      if (characterInput && settings.character) {
        characterInput.value = settings.character;
      }
      
      if (characterInfoInput && settings.character_info) {
        characterInfoInput.value = settings.character_info;
      }
      
      // Populate system prompt
      const systemPromptInput = document.getElementById('ai-system-prompt');
      if (systemPromptInput && settings.system_message) {
        systemPromptInput.value = settings.system_message;
      }
      
      // Populate custom instructions
      const customInstructionsInput = document.getElementById('ai-custom-instructions');
      if (customInstructionsInput && settings.custom_instructions) {
        customInstructionsInput.value = settings.custom_instructions;
      }
    })
    .catch(error => {
      console.error('Error loading global settings:', error);
      Toast.error('Failed to load AI settings. Please try again.');
    });
}
