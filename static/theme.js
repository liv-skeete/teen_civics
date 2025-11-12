/**
 * Theme management for dark/light mode
 * Persists user preference in localStorage
 */

// Initialize theme toggle button only (theme already set by inline script)
document.addEventListener('DOMContentLoaded', function() {
    // Set up theme toggle button if it exists
    setupThemeToggle();
});

/**
 * Set up theme toggle button functionality
 */
function setupThemeToggle() {
    const toggleButton = document.getElementById('theme-toggle');
    if (!toggleButton) return;
    
    // Update button text based on current theme
    updateToggleButtonText();
    
    // Add click event listener
    toggleButton.addEventListener('click', function() {
        toggleTheme();
    });
}

/**
 * Toggle between dark and light themes
 */
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    // Apply new theme
    document.documentElement.setAttribute('data-theme', newTheme);
    
    // Save preference
    localStorage.setItem('theme', newTheme);
    
    // Update toggle button text
    updateToggleButtonText();
}

/**
 * Update theme toggle button text based on current theme
 */
function updateToggleButtonText() {
    const toggleButton = document.getElementById('theme-toggle');
    if (!toggleButton) return;
    
    const currentTheme = document.documentElement.getAttribute('data-theme');
    toggleButton.setAttribute('aria-label', 
        currentTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
    
    // If button contains text, update it
    if (toggleButton.textContent) {
        toggleButton.textContent = 
            currentTheme === 'dark' ? 'Light Mode' : 'Dark Mode';
    }
}

/**
 * Apply theme immediately
 * @param {string} theme - 'dark' or 'light'
 */
function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    updateToggleButtonText();
}

// Export functions for use in other scripts
window.ThemeManager = {
    toggleTheme,
    applyTheme
};