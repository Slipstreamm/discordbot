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

  // Store selected guild ID globally (using localStorage)
  window.selectedGuildId = localStorage.getItem('selectedGuildId');
  window.currentSettingsGuildId = null; // Track which guild's settings are loaded
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

        // Get the section ID from the href (remove the # symbol)
        const sectionId = href.substring(1);

        // Show the section
        showSection(sectionId);

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

          // Show server selection screen first
          showServerSelection();
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
 * Show a specific section of the dashboard
 * @param {string} sectionId - The ID of the section to show (e.g., 'server-settings')
 */
function showSection(sectionId) {
  console.log(`Attempting to show section: ${sectionId}`);

  // Check if a server is selected before showing any section other than server-select
  if (!window.selectedGuildId && sectionId !== 'server-select') {
    console.log('No server selected, redirecting to server selection.');
    showServerSelection(); // Redirect to server selection
    return; // Stop further execution
  }

  // Hide all specific dashboard sections first
  document.querySelectorAll('.dashboard-section').forEach(section => {
    section.style.display = 'none';
  });
  // Also hide the server selection section if it exists and we are showing another section
  const serverSelectSection = document.getElementById('server-select-section');
  if (serverSelectSection && sectionId !== 'server-select') {
      serverSelectSection.style.display = 'none';
  }

  // Remove active class from all nav items
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.remove('active');
  });

  // Show the selected section
  const sectionElement = document.getElementById(`${sectionId}-section`);
  if (sectionElement) {
    sectionElement.style.display = 'block';
    console.log(`Successfully displayed section: ${sectionId}-section`);

    // Add active class to the corresponding nav item
    const navItem = document.querySelector(`.nav-item[data-section="${sectionId}-section"]`);
    if (navItem) {
      navItem.classList.add('active');
    }

    // Load data for the specific section if needed and a guild is selected
    if (window.selectedGuildId) {
        // Load AI settings if needed (assuming it's guild-specific now)
        if (sectionId === 'ai-settings' && typeof loadAiSettings === 'function') {
            // Check if already loaded for this guild to prevent redundant calls
            // This requires loadAiSettings to track its loaded state per guild or be idempotent
            console.log(`Loading AI settings for guild ${window.selectedGuildId}`);
            loadAiSettings(window.selectedGuildId); // Pass guildId
        }

        // Load theme settings if needed (assuming global/user-specific)
        if (sectionId === 'theme-settings' && typeof loadThemeSettings === 'function' && typeof themeSettingsLoaded !== 'undefined' && !themeSettingsLoaded) {
            console.log("Loading theme settings");
            loadThemeSettings();
            // themeSettingsLoaded = true; // Assuming loadThemeSettings handles this
        }

        // Load cog management if needed
        if (sectionId === 'cog-management' && typeof loadCogManagementData === 'function') {
             // Check if already loaded for this guild
             if (!window.cogManagementLoadedGuild || window.cogManagementLoadedGuild !== window.selectedGuildId) {
                console.log(`Loading Cog Management data for guild ${window.selectedGuildId}`);
                loadCogManagementData(window.selectedGuildId); // Pass guildId
                window.cogManagementLoadedGuild = window.selectedGuildId; // Track loaded guild
             } else {
                console.log(`Cog Management data for guild ${window.selectedGuildId} already loaded.`);
             }
        }

        // Load command customization if needed
        if (sectionId === 'command-customization' && typeof loadCommandCustomizationData === 'function') {
            // Check if already loaded for this guild
            if (!window.commandCustomizationLoadedGuild || window.commandCustomizationLoadedGuild !== window.selectedGuildId) {
                console.log(`Loading Command Customization data for guild ${window.selectedGuildId}`);
                loadCommandCustomizationData(window.selectedGuildId); // Pass guildId
                window.commandCustomizationLoadedGuild = window.selectedGuildId; // Track loaded guild
            } else {
                console.log(`Command Customization data for guild ${window.selectedGuildId} already loaded.`);
            }
        }

        // Load general server settings (prefix, welcome/leave, modules, permissions) if viewing relevant sections
        if (['server-settings', 'welcome-module', 'modules-settings', 'permissions-settings'].includes(sectionId)) {
            // loadGuildSettings already prevents redundant loads using window.currentSettingsGuildId
            console.log(`Loading general guild settings for guild ${window.selectedGuildId}`);
            loadGuildSettings(window.selectedGuildId);
        }
    }
  } else {
    console.warn(`Section with ID ${sectionId}-section not found.`);
    // Optionally show a default section or an error message
    // If no section found and a guild is selected, maybe default to server-settings?
    if (window.selectedGuildId) {
        console.log("Defaulting to server-settings section.");
        showSection('server-settings');
    } else {
        // If no guild selected either, go back to server selection
        showServerSelection();
    }
  }
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
 * Show the server selection screen
 */
function showServerSelection() {
  console.log('Showing server selection screen...');
  const dashboardContainer = document.getElementById('dashboard-container');
  const serverSelectSection = document.getElementById('server-select-section'); // Assuming this ID exists in index.html

  if (!serverSelectSection) {
    console.error('Server selection section not found!');
    // Maybe show an error to the user or default to the old behavior
    loadDashboardData(); // Fallback?
    return;
  }

  // Hide main dashboard content and show server selection
  if (dashboardContainer) dashboardContainer.style.display = 'none';
  serverSelectSection.style.display = 'block';

  // Hide all other specific dashboard sections just in case
  document.querySelectorAll('.dashboard-section').forEach(section => {
    section.style.display = 'none';
  });

  // Load the list of guilds for the user
  loadUserGuilds();
}

/**
 * Load guilds the user has admin access to for the selection screen
 */
function loadUserGuilds() {
  const serverListContainer = document.getElementById('server-list-container'); // Assuming this ID exists within server-select-section
  if (!serverListContainer) {
    console.error('Server list container not found!');
    return;
  }

  serverListContainer.innerHTML = '<div class="loading-spinner"></div><p>Loading your servers...</p>'; // Show loading state

  API.get('/dashboard/api/user-guilds')
    .then(guilds => {
      serverListContainer.innerHTML = ''; // Clear loading state

      if (!guilds || guilds.length === 0) {
        serverListContainer.innerHTML = '<p>No servers found where you have admin permissions.</p>';
        return;
      }

      guilds.forEach(guild => {
        const guildElement = document.createElement('div');
        guildElement.className = 'server-select-item card'; // Add card class for styling
        guildElement.style.cursor = 'pointer';
        guildElement.dataset.guildId = guild.id;

        const iconElement = document.createElement('img');
        iconElement.className = 'server-icon';
        iconElement.src = guild.icon_url || 'img/default-icon.png'; // Provide a default icon path
        iconElement.alt = `${guild.name} icon`;
        iconElement.width = 50;
        iconElement.height = 50;

        const nameElement = document.createElement('span');
        nameElement.className = 'server-name';
        nameElement.textContent = guild.name;

        guildElement.appendChild(iconElement);
        guildElement.appendChild(nameElement);

        guildElement.addEventListener('click', () => {
          console.log(`Server selected: ${guild.name} (${guild.id})`);
          // Store selected guild ID
          localStorage.setItem('selectedGuildId', guild.id);
          window.selectedGuildId = guild.id;
          window.currentSettingsGuildId = null; // Reset loaded settings tracker

          // Hide server selection and show dashboard
          const serverSelectSection = document.getElementById('server-select-section');
          const dashboardContainer = document.getElementById('dashboard-container');
          if (serverSelectSection) serverSelectSection.style.display = 'none';
          if (dashboardContainer) dashboardContainer.style.display = 'block';

          // Load data for the selected guild and show the default section
          loadDashboardData(); // Now loads data for the selected guild
          showSection('server-settings'); // Show the server settings section by default
        });

        serverListContainer.appendChild(guildElement);
      });
    })
    .catch(error => {
      console.error('Error loading user guilds:', error);
      serverListContainer.innerHTML = '<p class="text-danger">Error loading servers. Please try again.</p>';
      Toast.error('Failed to load your servers.');
    });
}


/**
 * Load initial dashboard data *after* a server has been selected
 */
function loadDashboardData() {
  if (!window.selectedGuildId) {
    console.warn('loadDashboardData called without a selected guild ID.');
    showServerSelection(); // Redirect back to selection if no guild is selected
    return;
  }
  console.log(`Loading dashboard data for guild: ${window.selectedGuildId}`);
  // No longer need to load the general guild list here.
  // Specific sections will load their data via showSection or dedicated functions.
  // We might load some initial settings common to multiple sections here if needed.
  // For now, let's ensure the basic settings are loaded if the user lands on a relevant page.
  loadGuildSettings(window.selectedGuildId);
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
 * Load guilds for the *original* server select dropdown (now potentially redundant)
 * Kept for reference or potential future use, but not called by default flow anymore.
 */
function loadGuilds() {
  console.warn("loadGuilds function called - this might be redundant now.");
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
 * Load settings for the currently selected guild (window.selectedGuildId)
 * @param {string} guildId - The guild ID to load settings for
 */
function loadGuildSettings(guildId) {
  // Prevent reloading if settings for this guild are already loaded
  if (window.currentSettingsGuildId === guildId) {
    console.log(`Settings for guild ${guildId} already loaded.`);
    // Ensure the forms are visible if navigating back
    const settingsForm = document.getElementById('settings-form');
    const welcomeSettingsForm = document.getElementById('welcome-settings-form');
    const modulesSettingsForm = document.getElementById('modules-settings-form');
    const permissionsSettingsForm = document.getElementById('permissions-settings-form');
    if (settingsForm) settingsForm.style.display = 'block';
    if (welcomeSettingsForm) welcomeSettingsForm.style.display = 'block';
    if (modulesSettingsForm) modulesSettingsForm.style.display = 'block';
    if (permissionsSettingsForm) permissionsSettingsForm.style.display = 'block';
    return;
  }
  console.log(`Loading settings for guild: ${guildId}`);

  const settingsForm = document.getElementById('settings-form');
  const welcomeSettingsForm = document.getElementById('welcome-settings-form');
  const modulesSettingsForm = document.getElementById('modules-settings-form');
  const permissionsSettingsForm = document.getElementById('permissions-settings-form');

  if (!settingsForm) return;

  // Show loading state
  const loadingContainer = document.createElement('div');
  loadingContainer.className = 'loading-container';
  loadingContainer.innerHTML = '<div class="loading-spinner"></div><p>Loading server settings...</p>';
  loadingContainer.style.textAlign = 'center';
  loadingContainer.style.padding = '2rem';

  // Hide all forms
  settingsForm.style.display = 'none';
  if (welcomeSettingsForm) welcomeSettingsForm.style.display = 'none';
  if (modulesSettingsForm) modulesSettingsForm.style.display = 'none';
  if (permissionsSettingsForm) permissionsSettingsForm.style.display = 'none';

  // Add loading indicator to server settings section
  settingsForm.parentNode.insertBefore(loadingContainer, settingsForm);

  // Fetch guild settings from API
  API.get(`/dashboard/api/guilds/${guildId}/settings`)
    .then(settings => {
      // Remove loading container
      loadingContainer.remove();

      // Show all settings forms
      settingsForm.style.display = 'block';
      if (welcomeSettingsForm) welcomeSettingsForm.style.display = 'block';
      if (modulesSettingsForm) modulesSettingsForm.style.display = 'block';
      if (permissionsSettingsForm) permissionsSettingsForm.style.display = 'block';

      // Populate forms with settings
      populateGuildSettings(settings);

      // Load additional data
      loadGuildChannels(guildId);
      loadGuildRoles(guildId);
      loadGuildCommands(guildId);

      // Mark settings as loaded for this guild
      window.currentSettingsGuildId = guildId;

      // Set up event listeners for buttons
      setupSaveSettingsButtons(guildId);
      setupWelcomeLeaveTestButtons(guildId);
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
 * Set up welcome/leave message test buttons
 * @param {string} guildId - The guild ID
 */
/**
 * Set up event listeners for save settings buttons
 * @param {string} guildId - The guild ID
 */
function setupSaveSettingsButtons(guildId) {
  // Save prefix button
  const savePrefixButton = document.getElementById('save-prefix-button');
  if (savePrefixButton) {
    savePrefixButton.addEventListener('click', () => {
      // Get prefix value
      const prefix = document.getElementById('prefix-input').value;
      if (!prefix) {
        Toast.error('Please enter a prefix');
        return;
      }

      // Show loading state
      savePrefixButton.disabled = true;
      savePrefixButton.classList.add('btn-loading');

      // Send request to API
      API.patch(`/dashboard/api/guilds/${guildId}/settings`, {
        prefix: prefix
      })
        .then(() => {
          // Show success message
          Toast.success('Prefix saved successfully');

          // Show feedback
          const prefixFeedback = document.getElementById('prefix-feedback');
          if (prefixFeedback) {
            prefixFeedback.textContent = 'Prefix saved successfully';
            prefixFeedback.className = 'success';

            // Clear feedback after a few seconds
            setTimeout(() => {
              prefixFeedback.textContent = '';
              prefixFeedback.className = '';
            }, 3000);
          }
        })
        .catch(error => {
          console.error('Error saving prefix:', error);
          Toast.error('Failed to save prefix. Please try again.');

          // Show error feedback
          const prefixFeedback = document.getElementById('prefix-feedback');
          if (prefixFeedback) {
            prefixFeedback.textContent = 'Error saving prefix. Please try again.';
            prefixFeedback.className = 'error';
          }
        })
        .finally(() => {
          // Remove loading state
          savePrefixButton.disabled = false;
          savePrefixButton.classList.remove('btn-loading');
        });
    });
  }

  // Save welcome settings button
  const saveWelcomeButton = document.getElementById('save-welcome-button');
  if (saveWelcomeButton) {
    saveWelcomeButton.addEventListener('click', () => {
      // Get welcome settings
      const welcomeChannelId = document.getElementById('welcome-channel').value;
      const welcomeMessage = document.getElementById('welcome-message').value;

      // Show loading state
      saveWelcomeButton.disabled = true;
      saveWelcomeButton.classList.add('btn-loading');

      // Send request to API
      API.patch(`/dashboard/api/guilds/${guildId}/settings`, {
        welcome_channel_id: welcomeChannelId,
        welcome_message: welcomeMessage
      })
        .then(() => {
          // Show success message
          Toast.success('Welcome settings saved successfully');

          // Show feedback
          const welcomeFeedback = document.getElementById('welcome-feedback');
          if (welcomeFeedback) {
            welcomeFeedback.textContent = 'Welcome settings saved successfully';
            welcomeFeedback.className = 'success';

            // Clear feedback after a few seconds
            setTimeout(() => {
              welcomeFeedback.textContent = '';
              welcomeFeedback.className = '';
            }, 3000);
          }
        })
        .catch(error => {
          console.error('Error saving welcome settings:', error);
          Toast.error('Failed to save welcome settings. Please try again.');

          // Show error feedback
          const welcomeFeedback = document.getElementById('welcome-feedback');
          if (welcomeFeedback) {
            welcomeFeedback.textContent = 'Error saving welcome settings. Please try again.';
            welcomeFeedback.className = 'error';
          }
        })
        .finally(() => {
          // Remove loading state
          saveWelcomeButton.disabled = false;
          saveWelcomeButton.classList.remove('btn-loading');
        });
    });
  }

  // Disable welcome button
  const disableWelcomeButton = document.getElementById('disable-welcome-button');
  if (disableWelcomeButton) {
    disableWelcomeButton.addEventListener('click', () => {
      // Confirm disable
      if (!confirm('Are you sure you want to disable welcome messages?')) {
        return;
      }

      // Show loading state
      disableWelcomeButton.disabled = true;
      disableWelcomeButton.classList.add('btn-loading');

      // Send request to API
      API.patch(`/dashboard/api/guilds/${guildId}/settings`, {
        welcome_channel_id: null,
        welcome_message: null
      })
        .then(() => {
          // Show success message
          Toast.success('Welcome messages disabled');

          // Clear welcome settings inputs
          const welcomeChannel = document.getElementById('welcome-channel');
          const welcomeMessage = document.getElementById('welcome-message');
          const welcomeChannelSelect = document.getElementById('welcome-channel-select');

          if (welcomeChannel) welcomeChannel.value = '';
          if (welcomeMessage) welcomeMessage.value = '';
          if (welcomeChannelSelect) welcomeChannelSelect.value = '';

          // Show feedback
          const welcomeFeedback = document.getElementById('welcome-feedback');
          if (welcomeFeedback) {
            welcomeFeedback.textContent = 'Welcome messages disabled';
            welcomeFeedback.className = 'success';

            // Clear feedback after a few seconds
            setTimeout(() => {
              welcomeFeedback.textContent = '';
              welcomeFeedback.className = '';
            }, 3000);
          }
        })
        .catch(error => {
          console.error('Error disabling welcome messages:', error);
          Toast.error('Failed to disable welcome messages. Please try again.');

          // Show error feedback
          const welcomeFeedback = document.getElementById('welcome-feedback');
          if (welcomeFeedback) {
            welcomeFeedback.textContent = 'Error disabling welcome messages. Please try again.';
            welcomeFeedback.className = 'error';
          }
        })
        .finally(() => {
          // Remove loading state
          disableWelcomeButton.disabled = false;
          disableWelcomeButton.classList.remove('btn-loading');
        });
    });
  }

  // Save goodbye settings button
  const saveGoodbyeButton = document.getElementById('save-goodbye-button');
  if (saveGoodbyeButton) {
    saveGoodbyeButton.addEventListener('click', () => {
      // Get goodbye settings
      const goodbyeChannelId = document.getElementById('goodbye-channel').value;
      const goodbyeMessage = document.getElementById('goodbye-message').value;

      // Show loading state
      saveGoodbyeButton.disabled = true;
      saveGoodbyeButton.classList.add('btn-loading');

      // Send request to API
      API.patch(`/dashboard/api/guilds/${guildId}/settings`, {
        goodbye_channel_id: goodbyeChannelId,
        goodbye_message: goodbyeMessage
      })
        .then(() => {
          // Show success message
          Toast.success('Goodbye settings saved successfully');

          // Show feedback
          const goodbyeFeedback = document.getElementById('goodbye-feedback');
          if (goodbyeFeedback) {
            goodbyeFeedback.textContent = 'Goodbye settings saved successfully';
            goodbyeFeedback.className = 'success';

            // Clear feedback after a few seconds
            setTimeout(() => {
              goodbyeFeedback.textContent = '';
              goodbyeFeedback.className = '';
            }, 3000);
          }
        })
        .catch(error => {
          console.error('Error saving goodbye settings:', error);
          Toast.error('Failed to save goodbye settings. Please try again.');

          // Show error feedback
          const goodbyeFeedback = document.getElementById('goodbye-feedback');
          if (goodbyeFeedback) {
            goodbyeFeedback.textContent = 'Error saving goodbye settings. Please try again.';
            goodbyeFeedback.className = 'error';
          }
        })
        .finally(() => {
          // Remove loading state
          saveGoodbyeButton.disabled = false;
          saveGoodbyeButton.classList.remove('btn-loading');
        });
    });
  }

  // Disable goodbye button
  const disableGoodbyeButton = document.getElementById('disable-goodbye-button');
  if (disableGoodbyeButton) {
    disableGoodbyeButton.addEventListener('click', () => {
      // Confirm disable
      if (!confirm('Are you sure you want to disable goodbye messages?')) {
        return;
      }

      // Show loading state
      disableGoodbyeButton.disabled = true;
      disableGoodbyeButton.classList.add('btn-loading');

      // Send request to API
      API.patch(`/dashboard/api/guilds/${guildId}/settings`, {
        goodbye_channel_id: null,
        goodbye_message: null
      })
        .then(() => {
          // Show success message
          Toast.success('Goodbye messages disabled');

          // Clear goodbye settings inputs
          const goodbyeChannel = document.getElementById('goodbye-channel');
          const goodbyeMessage = document.getElementById('goodbye-message');
          const goodbyeChannelSelect = document.getElementById('goodbye-channel-select');

          if (goodbyeChannel) goodbyeChannel.value = '';
          if (goodbyeMessage) goodbyeMessage.value = '';
          if (goodbyeChannelSelect) goodbyeChannelSelect.value = '';

          // Show feedback
          const goodbyeFeedback = document.getElementById('goodbye-feedback');
          if (goodbyeFeedback) {
            goodbyeFeedback.textContent = 'Goodbye messages disabled';
            goodbyeFeedback.className = 'success';

            // Clear feedback after a few seconds
            setTimeout(() => {
              goodbyeFeedback.textContent = '';
              goodbyeFeedback.className = '';
            }, 3000);
          }
        })
        .catch(error => {
          console.error('Error disabling goodbye messages:', error);
          Toast.error('Failed to disable goodbye messages. Please try again.');

          // Show error feedback
          const goodbyeFeedback = document.getElementById('goodbye-feedback');
          if (goodbyeFeedback) {
            goodbyeFeedback.textContent = 'Error disabling goodbye messages. Please try again.';
            goodbyeFeedback.className = 'error';
          }
        })
        .finally(() => {
          // Remove loading state
          disableGoodbyeButton.disabled = false;
          disableGoodbyeButton.classList.remove('btn-loading');
        });
    });
  }

  // Save cogs button
  const saveCogsButton = document.getElementById('save-cogs-button');
  if (saveCogsButton) {
    saveCogsButton.addEventListener('click', () => {
      // Get cog settings
      const cogsPayload = {};
      const cogCheckboxes = document.querySelectorAll('#cogs-list input[type="checkbox"]');

      cogCheckboxes.forEach(checkbox => {
        // Extract cog name from checkbox ID (format: cog-{name})
        const cogName = checkbox.id.replace('cog-', '');
        cogsPayload[cogName] = checkbox.checked;
      });

      // Show loading state
      saveCogsButton.disabled = true;
      saveCogsButton.classList.add('btn-loading');

      // Send request to API
      API.patch(`/dashboard/api/guilds/${guildId}/settings`, {
        cogs: cogsPayload
      })
        .then(() => {
          // Show success message
          Toast.success('Module settings saved successfully');

          // Show feedback
          const cogsFeedback = document.getElementById('cogs-feedback');
          if (cogsFeedback) {
            cogsFeedback.textContent = 'Module settings saved successfully';
            cogsFeedback.className = 'success';

            // Clear feedback after a few seconds
            setTimeout(() => {
              cogsFeedback.textContent = '';
              cogsFeedback.className = '';
            }, 3000);
          }
        })
        .catch(error => {
          console.error('Error saving module settings:', error);
          Toast.error('Failed to save module settings. Please try again.');

          // Show error feedback
          const cogsFeedback = document.getElementById('cogs-feedback');
          if (cogsFeedback) {
            cogsFeedback.textContent = 'Error saving module settings. Please try again.';
            cogsFeedback.className = 'error';
          }
        })
        .finally(() => {
          // Remove loading state
          saveCogsButton.disabled = false;
          saveCogsButton.classList.remove('btn-loading');
        });
    });
  }
}

function setupWelcomeLeaveTestButtons(guildId) {
  // Welcome message test button
  const testWelcomeButton = document.getElementById('test-welcome-button');
  if (testWelcomeButton) {
    testWelcomeButton.addEventListener('click', () => {
      // Show loading state
      testWelcomeButton.disabled = true;
      testWelcomeButton.classList.add('btn-loading');

      // Send test request to API
      API.post(`/dashboard/api/guilds/${guildId}/test-welcome`)
        .then(response => {
          console.log('Test welcome message response:', response);

          // Show success message with formatted message
          Toast.success('Test welcome message sent!');

          // Show formatted message in feedback area
          const welcomeFeedback = document.getElementById('welcome-feedback');
          if (welcomeFeedback) {
            welcomeFeedback.innerHTML = `
              <div class="mt-4 p-3 border rounded bg-light">
                <strong>Test Message:</strong>
                <p class="mb-0">${response.formatted_message}</p>
                <small class="text-muted">Sent to channel ID: ${response.channel_id}</small>
              </div>
            `;
          }
        })
        .catch(error => {
          console.error('Error testing welcome message:', error);

          // Show error message
          if (error.status === 400) {
            Toast.error('Welcome channel not configured. Please set a welcome channel first.');
          } else {
            Toast.error('Failed to test welcome message. Please try again.');
          }
        })
        .finally(() => {
          // Remove loading state
          testWelcomeButton.disabled = false;
          testWelcomeButton.classList.remove('btn-loading');
        });
    });
  }

  // Goodbye message test button
  const testGoodbyeButton = document.getElementById('test-goodbye-button');
  if (testGoodbyeButton) {
    testGoodbyeButton.addEventListener('click', () => {
      // Show loading state
      testGoodbyeButton.disabled = true;
      testGoodbyeButton.classList.add('btn-loading');

      // Send test request to API
      API.post(`/dashboard/api/guilds/${guildId}/test-goodbye`)
        .then(response => {
          console.log('Test goodbye message response:', response);

          // Show success message with formatted message
          Toast.success('Test goodbye message sent!');

          // Show formatted message in feedback area
          const goodbyeFeedback = document.getElementById('goodbye-feedback');
          if (goodbyeFeedback) {
            goodbyeFeedback.innerHTML = `
              <div class="mt-4 p-3 border rounded bg-light">
                <strong>Test Message:</strong>
                <p class="mb-0">${response.formatted_message}</p>
                <small class="text-muted">Sent to channel ID: ${response.channel_id}</small>
              </div>
            `;
          }
        })
        .catch(error => {
          console.error('Error testing goodbye message:', error);

          // Show error message
          if (error.status === 400) {
            Toast.error('Goodbye channel not configured. Please set a goodbye channel first.');
          } else {
            Toast.error('Failed to test goodbye message. Please try again.');
          }
        })
        .finally(() => {
          // Remove loading state
          testGoodbyeButton.disabled = false;
          testGoodbyeButton.classList.remove('btn-loading');
        });
    });
  }
}
