// TeenCivics JavaScript - Poll Voting and UI Interactions

document.addEventListener('DOMContentLoaded', function() {
    // Initialize all poll widgets on the page
    initializePollWidgets();
    
    // Set up mobile navigation toggle
    setupMobileNavigation();
    
    // Load any saved poll results
    loadPollResults();

    // Initialize archive mini-results widths (no inline styles)
    initArchiveMiniResults();
    
    // Initialize bill filtering on archive page
    initializeBillFiltering();
});

/**
 * Initialize all poll widgets on the page
 */
function initializePollWidgets() {
    const pollWidgets = document.querySelectorAll('.poll-widget');
    
    pollWidgets.forEach(widget => {
        const billId = widget.dataset.billId;
        const options = widget.querySelectorAll('.poll-option');
        const resultsContainer = widget.querySelector('.poll-results');
        const messageContainer = widget.querySelector('.poll-message');
        
        // If user already voted, highlight and load results
        const currentVote = localStorage.getItem(`voted_${billId}`);
        if (currentVote) {
            highlightCurrentVote(options, currentVote);
            fetchAndDisplayResults(billId, widget);
        }
        
        // Always set click handlers; compute latest stored vote at click time
        options.forEach(option => {
            option.addEventListener('click', function() {
                const voteType = this.dataset.vote;
                const storedVote = localStorage.getItem(`voted_${billId}`);
                
                // If clicking same as stored, no-op to avoid double-increment
                if (storedVote && voteType === storedVote) {
                    // Subtle, non-intrusive message then hide
                    if (messageContainer) {
                        showLoadingMessage(messageContainer, 'You already selected this option.');
                        setTimeout(() => { messageContainer.style.display = 'none'; }, 1200);
                    }
                    return;
                }
                
                handleVote(billId, voteType, widget, storedVote || null);
            });
        });
    });
}

/**
 * Handle voting process
 */
function handleVote(billId, voteType, widget, previousVote) {
    const options = widget.querySelectorAll('.poll-option');
    const messageContainer = widget.querySelector('.poll-message');
    const resultsContainer = widget.querySelector('.poll-results');
    
    // Show loading state
    disablePollOptions(options);
    showLoadingMessage(messageContainer, 'Recording your vote...');
    
    /* Send vote to server with robust error handling */
    fetch('/api/vote', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            bill_id: billId,
            vote_type: voteType,
            previous_vote: previousVote  // Send previous vote for change tracking
        })
    })
    .then(async (response) => {
        let data = {};
        try {
            data = await response.json();
        } catch (_) {
            // Non-JSON response
        }
        if (!response.ok || !data.success) {
            const msg = (data && data.error) ? data.error : `Failed to record vote (HTTP ${response.status})`;
            throw new Error(msg);
        }
        return data;
    })
    .then((data) => {
        // Vote successful
        const isChange = !!previousVote && previousVote !== voteType;
        if (isChange) {
            showSuccessMessage(messageContainer, 'Vote changed successfully!');
        } else {
            showSuccessMessage(messageContainer, 'Thanks for voting!');
        }
        
        // Persist new vote locally
        localStorage.setItem(`voted_${billId}`, voteType);
    
        // Update UI to show new selection
        highlightCurrentVote(options, voteType);
        
        // Update results immediately from response if available; fall back to fetch
        if (data && data.results && resultsContainer) {
            updateResultsDisplay(data.results, resultsContainer);
            resultsContainer.style.display = 'block';
        } else {
            fetchAndDisplayResults(billId, widget);
        }
    })
    .catch(error => {
        console.error('Vote error:', error);
        showErrorMessage(messageContainer, error.message || 'Network error. Please check your connection and try again.');
    })
    .finally(() => {
        // Always re-enable options after request completes
        enablePollOptions(options);
    });
}

/**
 * Fetch and display poll results
 */
function fetchAndDisplayResults(billId, widget) {
    const resultsContainer = widget.querySelector('.poll-results');
    const messageContainer = widget.querySelector('.poll-message');
    
    showLoadingMessage(messageContainer, 'Loading results...');
    
    /* Fetch results with robust error handling */
    fetch(`/api/poll-results/${billId}`)
    .then(async (response) => {
        let data = {};
        try {
            data = await response.json();
        } catch (_) {
            // Non-JSON response
        }
        if (!response.ok || (data && data.error)) {
            const msg = (data && data.error) ? data.error : `Failed to load results (HTTP ${response.status})`;
            throw new Error(msg);
        }
        return data;
    })
    .then(results => {
        // Update results display
        updateResultsDisplay(results, resultsContainer);
    
        // Show results container
        resultsContainer.style.display = 'block';
        messageContainer.style.display = 'none';
    })
    .catch(error => {
        console.error('Error fetching results:', error);
        showErrorMessage(messageContainer, error.message || 'Failed to load results. Please refresh the page.');
    });
}

/**
 * Update the results display with new data (yes/no only)
 */
function updateResultsDisplay(results, container) {
    const yes = Number(results.yes_votes || 0);
    const no = Number(results.no_votes || 0);
    const total = Number(results.total != null ? results.total : (yes + no));

    // Calculate percentages safely
    const pct = (n, d) => d > 0 ? Math.max(0, Math.min(100, (n / d) * 100)) : 0;
    const yesPercent = pct(yes, total);
    const noPercent = pct(no, total);

    // Update result bars
    const yesFill = container.querySelector('.yes-fill');
    const noFill = container.querySelector('.no-fill');

    if (yesFill) yesFill.style.width = `${yesPercent}%`;
    if (noFill) noFill.style.width = `${noPercent}%`;

    // Update counts (locate count spans within each bar)
    const yesCountEl = yesFill ? yesFill.querySelector('.result-count') : null;
    const noCountEl = noFill ? noFill.querySelector('.result-count') : null;

    if (yesCountEl) yesCountEl.textContent = yes;
    if (noCountEl) noCountEl.textContent = no;

    const totalEl = container.querySelector('.votes-count');
    if (totalEl) totalEl.textContent = total;
}

/**
 * Disable poll options to prevent multiple votes
 */
function disablePollOptions(options) {
    options.forEach(option => {
        option.disabled = true;
        option.style.opacity = '0.6';
        option.style.cursor = 'not-allowed';
    });
}

/**
 * Enable poll options for voting
 */
function enablePollOptions(options) {
    options.forEach(option => {
        option.disabled = false;
        option.style.opacity = '1';
        option.style.cursor = 'pointer';
    });
}

/**
 * Show loading message
 */
function showLoadingMessage(container, message) {
    container.textContent = message;
    container.className = 'poll-message';
    container.style.display = 'block';
}

/**
 * Show success message
 */
function showSuccessMessage(container, message) {
    container.textContent = message;
    container.className = 'poll-message success';
    container.style.display = 'block';
    
    // Auto-hide success message after 3 seconds
    setTimeout(() => {
        container.style.display = 'none';
    }, 3000);
}

/**
 * Show error message
 */
function showErrorMessage(container, message) {
    container.textContent = message;
    container.className = 'poll-message error';
    container.style.display = 'block';
}

/**
 * Set up mobile navigation toggle
 */
function setupMobileNavigation() {
    const navToggle = document.querySelector('.nav-toggle');
    const navMenu = document.querySelector('.nav-menu');
    
    console.log('[DEBUG] Mobile nav setup:', { navToggle: !!navToggle, navMenu: !!navMenu });
    
    if (navToggle && navMenu) {
        navToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            const isExpanded = navMenu.classList.contains('active');
            
            navMenu.classList.toggle('active');
            console.log('[DEBUG] Nav toggled, active:', !isExpanded);
            
            // Update ARIA attribute
            navToggle.setAttribute('aria-expanded', !isExpanded);
            
            // Animate hamburger icon
            const bars = navToggle.querySelectorAll('.bar');
            bars.forEach(bar => bar.classList.toggle('active'));
        });
    }
    
    // Close mobile menu when clicking outside
    document.addEventListener('click', function(event) {
        if (navMenu && navMenu.classList.contains('active') &&
            !event.target.closest('.nav-menu') &&
            !event.target.closest('.nav-toggle')) {
            navMenu.classList.remove('active');
            navToggle.setAttribute('aria-expanded', 'false');
            const bars = navToggle.querySelectorAll('.bar');
            bars.forEach(bar => bar.classList.remove('active'));
        }
    });
    
    // Close mobile menu when clicking a nav link
    if (navMenu) {
        const navLinks = navMenu.querySelectorAll('.nav-link');
        navLinks.forEach(link => {
            link.addEventListener('click', function() {
                navMenu.classList.remove('active');
                navToggle.setAttribute('aria-expanded', 'false');
                const bars = navToggle.querySelectorAll('.bar');
                bars.forEach(bar => bar.classList.remove('active'));
            });
        });
    }
}

/**
 * Load and display any previously fetched poll results
 */
function loadPollResults() {
    const pollWidgets = document.querySelectorAll('.poll-widget');
    
    pollWidgets.forEach(widget => {
        const billId = widget.dataset.billId;
        const currentVote = localStorage.getItem(`voted_${billId}`);
        const options = widget.querySelectorAll('.poll-option');
        
        if (currentVote) {
            // User voted before, show results and highlight selection
            const resultsContainer = widget.querySelector('.poll-results');
            resultsContainer.style.display = 'block';
            highlightCurrentVote(options, currentVote);
            fetchAndDisplayResults(billId, widget);
        }
    });
}

/**
 * Highlight the user's current vote selection
 */
function highlightCurrentVote(options, currentVote) {
    options.forEach(option => {
        if (option.dataset.vote === currentVote) {
            option.classList.add('selected');
            option.style.cursor = 'default';
            option.title = 'Your current vote (click another option to change)';
        } else {
            option.classList.remove('selected');
            option.style.cursor = 'pointer';
            option.title = '';
        }
    });
}

/**
 * Initialize archive mini-results bars using data attributes
 * This avoids inline styles that confuse the CSS linter in templates.
 */
function initArchiveMiniResults() {
    const containers = document.querySelectorAll('.mini-results');
    containers.forEach(c => {
        const yes = parseFloat(c.dataset.yes || '0');
        const no = parseFloat(c.dataset.no || '0');
        const yesEl = c.querySelector('.mini-result.yes');
        const noEl = c.querySelector('.mini-result.no');
        if (yesEl && !isNaN(yes)) {
            yesEl.style.width = `${Math.max(0, Math.min(100, yes))}%`;
        }
        if (noEl && !isNaN(no)) {
            noEl.style.width = `${Math.max(0, Math.min(100, no))}%`;
        }
    });
}

/**
 * Initialize bill filtering on archive page
 */
function initializeBillFiltering() {
    const filterSelect = document.getElementById('status-filter');
    const sortCheckbox = document.getElementById('sort-by-impact');
    
    if (!filterSelect) {
        return; // Not on archive page
    }
    
    console.log('[DEBUG] Initializing bill filtering');
    
    // Load saved filter from localStorage or URL parameter
    const urlParams = new URLSearchParams(window.location.search);
    const urlStatus = urlParams.get('status');
    
    // Set initial filter value from URL if present
    if (urlStatus) {
        filterSelect.value = urlStatus;
        console.log('[DEBUG] Set filter from URL:', urlStatus);
    }
    
    // Add change event listener for status filter - reload page with new filter
    filterSelect.addEventListener('change', function() {
        const selectedStatus = this.value;
        console.log('[DEBUG] Filter changed to:', selectedStatus);
        
        // Save filter preference
        localStorage.setItem('archive_filter', selectedStatus);
        
        // Reload page with new filter parameter, preserving 'q'
        const newUrl = new URL(window.location);
        if (selectedStatus === 'all') {
            newUrl.searchParams.delete('status');
        } else {
            newUrl.searchParams.set('status', selectedStatus);
        }
        // Reset to page 1 when filter changes
        newUrl.searchParams.delete('page');
        
        // Reload the page to apply server-side filtering
        window.location.href = newUrl.toString();
    });
    
    // Add change event listener for teen impact score sorting
    if (sortCheckbox) {
        sortCheckbox.addEventListener('change', function() {
            console.log('[DEBUG] Sort checkbox changed:', this.checked);
            sortBillsByTeenImpact(this.checked);
        });
    }
}

/**
 * Filter bills by status
 */
function filterBills(status) {
    const billCards = document.querySelectorAll('.bill-card');
    const noBillsMessage = document.querySelector('.no-bills-message');
    let visibleCount = 0;
    
    console.log('[DEBUG] Filtering bills by status:', status);
    console.log('[DEBUG] Found bill cards:', billCards.length);
    
    // Normalize status for comparison (case-insensitive)
    const normalizedStatus = status.toLowerCase();
    
    billCards.forEach(card => {
        const cardStatus = (card.dataset.status || '').toLowerCase();
        console.log('[DEBUG] Card status:', cardStatus, 'matches:', normalizedStatus === 'all' || cardStatus === normalizedStatus);
        
        if (normalizedStatus === 'all' || cardStatus === normalizedStatus) {
            card.style.display = '';
            visibleCount++;
        } else {
            card.style.display = 'none';
        }
    });
    
    console.log('[DEBUG] Visible count:', visibleCount);
    
    // Show/hide "no bills" message
    const billsGrid = document.querySelector('.bills-grid');
    if (visibleCount === 0 && billsGrid) {
        if (!noBillsMessage) {
            // Create no bills message if it doesn't exist
            const message = document.createElement('div');
            message.className = 'no-bills-message';
            message.innerHTML = `
                <h2>No bills found</h2>
                <p>No bills with status "${status}" found.</p>
                <button class="btn btn-primary" onclick="document.getElementById('status-filter').value='all'; document.getElementById('status-filter').dispatchEvent(new Event('change'));">View All Bills</button>
            `;
            billsGrid.parentNode.insertBefore(message, billsGrid.nextSibling);
        } else {
            noBillsMessage.style.display = 'block';
            const messageText = noBillsMessage.querySelector('p');
            if (messageText && status !== 'all') {
                messageText.textContent = `No bills with status "${status}" found.`;
            }
        }
        billsGrid.style.display = 'none';
    } else {
        if (noBillsMessage) {
            noBillsMessage.style.display = 'none';
        }
        if (billsGrid) {
            billsGrid.style.display = '';
        }
    }
}

/**
 * Sort bills by teen impact score (highest to lowest)
 */
function sortBillsByTeenImpact(sortEnabled) {
    const billsGrid = document.querySelector('.bills-grid');
    
    console.log('[DEBUG] Sort by teen impact:', sortEnabled);
    
    if (!billsGrid) {
        console.log('[DEBUG] Bills grid not found');
        return; // Not on archive page
    }
    
    // Get all bill cards (only visible ones)
    const billCards = Array.from(billsGrid.querySelectorAll('.bill-card'));
    console.log('[DEBUG] Found bill cards for sorting:', billCards.length);
    
    if (billCards.length === 0) {
        console.log('[DEBUG] No bill cards to sort');
        return;
    }
    
    if (sortEnabled) {
        // Sort by teen impact score (highest to lowest)
        billCards.sort((a, b) => {
            const scoreA = parseFloat(a.dataset.teenImpact) || -1;
            const scoreB = parseFloat(b.dataset.teenImpact) || -1;
            console.log('[DEBUG] Comparing:', a.querySelector('.bill-title')?.textContent?.substring(0, 30), 'score:', scoreA, 'vs', b.querySelector('.bill-title')?.textContent?.substring(0, 30), 'score:', scoreB);
            
            // Bills with scores come first, sorted highest to lowest
            // Bills without scores come last, in their original order
            if (scoreA === -1 && scoreB === -1) return 0;
            if (scoreA === -1) return 1;
            if (scoreB === -1) return -1;
            return scoreB - scoreA;
        });
    } else {
        // Restore original order by date_processed (most recent first)
        // Since bills are already in the correct order in the DOM initially,
        // we can sort by their original index
        billCards.sort((a, b) => {
            const indexA = parseInt(a.dataset.originalIndex) || 0;
            const indexB = parseInt(b.dataset.originalIndex) || 0;
            console.log('[DEBUG] Restoring order:', indexA, 'vs', indexB);
            return indexA - indexB;
        });
    }
    
    console.log('[DEBUG] Reordering', billCards.length, 'cards in the DOM');
    
    // Clear the grid and re-append cards in sorted order
    billsGrid.innerHTML = '';
    billCards.forEach(card => {
        billsGrid.appendChild(card);
    });
    
    console.log('[DEBUG] Sort complete');
}

/**
 * Utility function for smooth scrolling
 */
function smoothScrollTo(element) {
    element.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
    });
}

/**
 * Debounce function for resize events
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Add resize handler for responsive adjustments
window.addEventListener('resize', debounce(function() {
    // Close mobile menu on resize to larger screens
    const navMenu = document.querySelector('.nav-menu');
    const navToggle = document.querySelector('.nav-toggle');
    
    if (window.innerWidth > 768 && navMenu && navMenu.classList.contains('active')) {
        navMenu.classList.remove('active');
        const bars = navToggle.querySelectorAll('.bar');
        bars.forEach(bar => bar.classList.remove('active'));
    }
}, 250));

// Mobile menu animation styles are now in style.css to avoid conflicts