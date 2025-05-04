/**
 * Utility functions for the Discord Bot Dashboard
 */

// Toast notification system
const Toast = {
  container: null,

  /**
   * Initialize the toast container
   */
  init() {
    // Create toast container if it doesn't exist
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.className = 'toast-container';
      document.body.appendChild(this.container);
    }
  },

  /**
   * Show a toast notification
   * @param {string} message - The message to display
   * @param {string} type - The type of toast (success, error, warning, info)
   * @param {string} title - Optional title for the toast
   * @param {number} duration - Duration in milliseconds before auto-hiding
   */
  show(message, type = 'info', title = '', duration = 5000) {
    this.init();

    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    // Create icon based on type
    let iconSvg = '';
    switch (type) {
      case 'success':
        iconSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#48BB78" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>';
        break;
      case 'error':
        iconSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#F56565" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>';
        break;
      case 'warning':
        iconSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#F6AD55" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>';
        break;
      default: // info
        iconSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#5865F2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';
    }

    // Set toast content
    toast.innerHTML = `
      <div class="toast-icon">${iconSvg}</div>
      <div class="toast-content">
        ${title ? `<div class="toast-title">${title}</div>` : ''}
        <div class="toast-message">${message}</div>
      </div>
      <button class="toast-close">&times;</button>
    `;

    // Add to container
    this.container.appendChild(toast);

    // Add close event
    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => this.hide(toast));

    // Auto-hide after duration
    if (duration) {
      setTimeout(() => this.hide(toast), duration);
    }

    return toast;
  },

  /**
   * Hide a toast notification
   * @param {HTMLElement} toast - The toast element to hide
   */
  hide(toast) {
    toast.classList.add('toast-hiding');
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 300); // Match animation duration
  },

  /**
   * Show a success toast
   * @param {string} message - The message to display
   * @param {string} title - Optional title
   */
  success(message, title = 'Success') {
    return this.show(message, 'success', title);
  },

  /**
   * Show an error toast
   * @param {string} message - The message to display
   * @param {string} title - Optional title
   */
  error(message, title = 'Error') {
    return this.show(message, 'error', title);
  },

  /**
   * Show a warning toast
   * @param {string} message - The message to display
   * @param {string} title - Optional title
   */
  warning(message, title = 'Warning') {
    return this.show(message, 'warning', title);
  },

  /**
   * Show an info toast
   * @param {string} message - The message to display
   * @param {string} title - Optional title
   */
  info(message, title = 'Info') {
    return this.show(message, 'info', title);
  }
};

// API utilities
const API = {
  /**
   * Make an API request with loading state
   * @param {string} url - The API endpoint URL
   * @param {Object} options - Fetch options
   * @param {HTMLElement} loadingElement - Element to show loading state on
   * @param {number} retryCount - Internal parameter for tracking retries
   * @returns {Promise} - The fetch promise
   */
  async request(url, options = {}, loadingElement = null, retryCount = 0) {
    // Set default headers
    options.headers = options.headers || {};
    options.headers['Content-Type'] = options.headers['Content-Type'] || 'application/json';

    // Always include credentials for session cookies
    options.credentials = options.credentials || 'same-origin';

    // Maximum number of retries for rate-limited requests
    const MAX_RETRIES = 3;

    // Add loading state
    if (loadingElement) {
      if (loadingElement.tagName === 'BUTTON') {
        loadingElement.disabled = true;
        loadingElement.classList.add('btn-loading');
      } else {
        // Create or use existing loading overlay
        let overlay = loadingElement.querySelector('.loading-overlay');
        if (!overlay) {
          overlay = document.createElement('div');
          overlay.className = 'loading-overlay';
          overlay.innerHTML = '<div class="loading-spinner"></div>';

          // Make sure the element has position relative for absolute positioning
          const computedStyle = window.getComputedStyle(loadingElement);
          if (computedStyle.position === 'static') {
            loadingElement.style.position = 'relative';
          }

          loadingElement.appendChild(overlay);
        } else {
          overlay.style.display = 'flex';
        }
      }
    }

    try {
      console.log(`API Request: ${options.method || 'GET'} ${url}${retryCount > 0 ? ` (Retry ${retryCount}/${MAX_RETRIES})` : ''}`);
      const response = await fetch(url, options);
      console.log(`API Response: ${response.status} ${response.statusText}`);

      // Check rate limit headers and log them for monitoring
      const rateLimit = {
        limit: response.headers.get('X-RateLimit-Limit'),
        remaining: response.headers.get('X-RateLimit-Remaining'),
        reset: response.headers.get('X-RateLimit-Reset'),
        resetAfter: response.headers.get('X-RateLimit-Reset-After'),
        bucket: response.headers.get('X-RateLimit-Bucket')
      };

      // If we're getting close to the rate limit, log a warning
      if (rateLimit.remaining && parseInt(rateLimit.remaining) < 5) {
        console.warn(`API Rate limit warning: ${rateLimit.remaining}/${rateLimit.limit} requests remaining in bucket ${rateLimit.bucket}. Resets in ${rateLimit.resetAfter}s`);
      }

      // Handle rate limiting with automatic retry
      if (response.status === 429 && retryCount < MAX_RETRIES) {
        // Get the most accurate retry time from headers
        let retryAfter = parseFloat(
          response.headers.get('X-RateLimit-Reset-After') ||
          response.headers.get('Retry-After') ||
          Math.pow(2, retryCount)
        );

        // Check if this is a global rate limit
        const isGlobal = response.headers.get('X-RateLimit-Global') !== null;

        // Get the rate limit scope if available
        const scope = response.headers.get('X-RateLimit-Scope') || 'unknown';

        // For global rate limits, we might want to wait longer
        if (isGlobal) {
          retryAfter = Math.max(retryAfter, 5);  // At least 5 seconds for global limits
        }

        console.log(`Rate limited (${isGlobal ? 'Global' : 'Route'}, Scope: ${scope}). Retrying in ${retryAfter} seconds...`);

        // Show toast with more detailed information
        if (retryCount === 0) {
          const message = isGlobal
            ? `Discord API global rate limit hit. Retrying in ${retryAfter} seconds...`
            : `Rate limited by Discord API. Retrying in ${retryAfter} seconds...`;

          Toast.warning(message, 'Please Wait');
        }

        // Wait for the specified time
        await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));

        // Retry the request
        return this.request(url, options, loadingElement, retryCount + 1);
      }

      // Parse JSON response
      let data;
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        data = await response.json();
      } else {
        data = await response.text();
      }

      // Remove loading state
      if (loadingElement) {
        if (loadingElement.tagName === 'BUTTON') {
          loadingElement.disabled = false;
          loadingElement.classList.remove('btn-loading');
        } else {
          const overlay = loadingElement.querySelector('.loading-overlay');
          if (overlay) {
            overlay.style.display = 'none';
          }
        }
      }

      // Handle error responses
      if (!response.ok) {
        const errorMessage = data.detail || data.message || data.error || 'API request failed';
        console.error(`API Error (${response.status}): ${errorMessage}`, data);

        const error = new Error(errorMessage);
        error.status = response.status;
        error.data = data;

        // Handle specific error types
        if (response.status === 401) {
          console.log('Authentication error detected, redirecting to login');
          // Redirect to login after a short delay to show the error
          setTimeout(() => {
            window.location.href = '/dashboard/api/auth/login';
          }, 2000);
        }
        else if (response.status === 429) {
          // Get rate limit information from headers
          const retryAfter = parseFloat(
            response.headers.get('X-RateLimit-Reset-After') ||
            response.headers.get('Retry-After') ||
            '60'
          );

          const isGlobal = response.headers.get('X-RateLimit-Global') !== null;
          const scope = response.headers.get('X-RateLimit-Scope') || 'unknown';
          const bucket = response.headers.get('X-RateLimit-Bucket') || 'unknown';

          // Log detailed rate limit information
          console.log(`Rate limit hit: Global=${isGlobal}, Scope=${scope}, Bucket=${bucket}, Retry=${retryAfter}s`);

          // Show appropriate message based on rate limit type
          if (isGlobal) {
            Toast.warning(
              `Discord API global rate limit reached. Please wait ${Math.ceil(retryAfter)} seconds before trying again.`,
              'Global Rate Limit'
            );
          } else {
            Toast.warning(
              `Discord API rate limit reached. Please wait ${Math.ceil(retryAfter)} seconds before trying again.`,
              'Rate Limited'
            );
          }
        }

        throw error;
      }

      return data;
    } catch (error) {
      // Remove loading state
      if (loadingElement) {
        if (loadingElement.tagName === 'BUTTON') {
          loadingElement.disabled = false;
          loadingElement.classList.remove('btn-loading');
        } else {
          const overlay = loadingElement.querySelector('.loading-overlay');
          if (overlay) {
            overlay.style.display = 'none';
          }
        }
      }

      // Show error toast
      Toast.error(error.message || 'An error occurred');

      throw error;
    }
  },

  /**
   * Make a GET request
   * @param {string} url - The API endpoint URL
   * @param {HTMLElement} loadingElement - Element to show loading state on
   * @returns {Promise} - The fetch promise
   */
  async get(url, loadingElement = null) {
    return this.request(url, { method: 'GET' }, loadingElement);
  },

  /**
   * Make a POST request
   * @param {string} url - The API endpoint URL
   * @param {Object} data - The data to send
   * @param {HTMLElement} loadingElement - Element to show loading state on
   * @returns {Promise} - The fetch promise
   */
  async post(url, data, loadingElement = null) {
    return this.request(
      url,
      {
        method: 'POST',
        body: JSON.stringify(data)
      },
      loadingElement
    );
  },

  /**
   * Make a PUT request
   * @param {string} url - The API endpoint URL
   * @param {Object} data - The data to send
   * @param {HTMLElement} loadingElement - Element to show loading state on
   * @returns {Promise} - The fetch promise
   */
  async put(url, data, loadingElement = null) {
    return this.request(
      url,
      {
        method: 'PUT',
        body: JSON.stringify(data)
      },
      loadingElement
    );
  },

  /**
   * Make a DELETE request
   * @param {string} url - The API endpoint URL
   * @param {HTMLElement} loadingElement - Element to show loading state on
   * @returns {Promise} - The fetch promise
   */
  async delete(url, loadingElement = null) {
    return this.request(url, { method: 'DELETE' }, loadingElement);
  }
};

// Modal utilities
const Modal = {
  /**
   * Open a modal
   * @param {string} modalId - The ID of the modal to open
   */
  open(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.add('active');
      document.body.style.overflow = 'hidden'; // Prevent scrolling
    }
  },

  /**
   * Close a modal
   * @param {string} modalId - The ID of the modal to close
   */
  close(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.remove('active');
      document.body.style.overflow = ''; // Restore scrolling
    }
  },

  /**
   * Initialize modal close buttons
   */
  init() {
    // Close modal when clicking the close button
    document.querySelectorAll('.modal-close').forEach(button => {
      button.addEventListener('click', () => {
        const modal = button.closest('.modal');
        if (modal) {
          modal.classList.remove('active');
          document.body.style.overflow = ''; // Restore scrolling
        }
      });
    });

    // Close modal when clicking outside the modal content
    document.querySelectorAll('.modal').forEach(modal => {
      modal.addEventListener('click', (event) => {
        if (event.target === modal) {
          modal.classList.remove('active');
          document.body.style.overflow = ''; // Restore scrolling
        }
      });
    });
  }
};

// Form utilities
const Form = {
  /**
   * Serialize form data to an object
   * @param {HTMLFormElement} form - The form element
   * @returns {Object} - The serialized form data
   */
  serialize(form) {
    const formData = new FormData(form);
    const data = {};

    for (const [key, value] of formData.entries()) {
      // Handle checkboxes
      if (form.elements[key].type === 'checkbox') {
        data[key] = value === 'on';
      } else {
        data[key] = value;
      }
    }

    return data;
  },

  /**
   * Populate a form with data
   * @param {HTMLFormElement} form - The form element
   * @param {Object} data - The data to populate the form with
   */
  populate(form, data) {
    for (const key in data) {
      if (form.elements[key]) {
        const element = form.elements[key];

        if (element.type === 'checkbox') {
          element.checked = Boolean(data[key]);
        } else if (element.type === 'radio') {
          const radio = form.querySelector(`input[name="${key}"][value="${data[key]}"]`);
          if (radio) {
            radio.checked = true;
          }
        } else {
          element.value = data[key];
        }

        // Trigger change event for elements like select
        const event = new Event('change');
        element.dispatchEvent(event);
      }
    }
  },

  /**
   * Validate a form
   * @param {HTMLFormElement} form - The form element
   * @returns {boolean} - Whether the form is valid
   */
  validate(form) {
    let isValid = true;

    // Remove existing error messages
    form.querySelectorAll('.form-error').forEach(error => {
      error.remove();
    });

    // Check required fields
    form.querySelectorAll('[required]').forEach(field => {
      if (!field.value.trim()) {
        isValid = false;
        this.showError(field, 'This field is required');
      }
    });

    // Check email fields
    form.querySelectorAll('input[type="email"]').forEach(field => {
      if (field.value && !this.isValidEmail(field.value)) {
        isValid = false;
        this.showError(field, 'Please enter a valid email address');
      }
    });

    return isValid;
  },

  /**
   * Show an error message for a form field
   * @param {HTMLElement} field - The form field
   * @param {string} message - The error message
   */
  showError(field, message) {
    // Create error message element
    const error = document.createElement('div');
    error.className = 'form-error';
    error.textContent = message;
    error.style.color = 'var(--danger-color)';
    error.style.fontSize = '0.875rem';
    error.style.marginTop = '0.25rem';

    // Add error class to field
    field.classList.add('is-invalid');

    // Insert error after field
    field.parentNode.insertBefore(error, field.nextSibling);

    // Add event listener to remove error when field is changed
    field.addEventListener('input', () => {
      field.classList.remove('is-invalid');
      if (error.parentNode) {
        error.parentNode.removeChild(error);
      }
    }, { once: true });
  },

  /**
   * Check if an email is valid
   * @param {string} email - The email to check
   * @returns {boolean} - Whether the email is valid
   */
  isValidEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
  }
};

// DOM utilities
const DOM = {
  /**
   * Create an element with attributes and children
   * @param {string} tag - The tag name
   * @param {Object} attrs - The attributes
   * @param {Array|string} children - The children
   * @returns {HTMLElement} - The created element
   */
  createElement(tag, attrs = {}, children = []) {
    const element = document.createElement(tag);

    // Set attributes
    for (const key in attrs) {
      if (key === 'className') {
        element.className = attrs[key];
      } else if (key === 'style' && typeof attrs[key] === 'object') {
        Object.assign(element.style, attrs[key]);
      } else if (key.startsWith('on') && typeof attrs[key] === 'function') {
        const eventName = key.substring(2).toLowerCase();
        element.addEventListener(eventName, attrs[key]);
      } else {
        element.setAttribute(key, attrs[key]);
      }
    }

    // Add children
    if (Array.isArray(children)) {
      children.forEach(child => {
        if (typeof child === 'string') {
          element.appendChild(document.createTextNode(child));
        } else if (child instanceof Node) {
          element.appendChild(child);
        }
      });
    } else if (typeof children === 'string') {
      element.textContent = children;
    }

    return element;
  },

  /**
   * Create a loading spinner
   * @param {string} size - The size of the spinner (sm, md, lg)
   * @returns {HTMLElement} - The spinner element
   */
  createSpinner(size = 'md') {
    const spinner = document.createElement('div');
    spinner.className = `loading-spinner loading-spinner-${size}`;
    return spinner;
  },

  /**
   * Show a loading spinner in a container
   * @param {HTMLElement} container - The container element
   * @param {string} size - The size of the spinner
   * @returns {HTMLElement} - The spinner container element
   */
  showSpinner(container, size = 'md') {
    // Clear container
    container.innerHTML = '';

    // Create spinner container
    const spinnerContainer = document.createElement('div');
    spinnerContainer.className = 'loading-spinner-container';

    // Create spinner
    const spinner = this.createSpinner(size);
    spinnerContainer.appendChild(spinner);

    // Add to container
    container.appendChild(spinnerContainer);

    return spinnerContainer;
  }
};

// Export utilities
window.Toast = Toast;
window.API = API;
window.Modal = Modal;
window.Form = Form;
window.DOM = DOM;
