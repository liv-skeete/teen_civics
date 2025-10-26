// TeenCivics JavaScript - Poll Voting, UI Interactions, and Archive Utilities
// Optimized to avoid duplicate /api/poll-results calls and reduce redundant work.

(() => {
  "use strict";

  // --- Config ---
  const DEBUG = false;

  // --- Internal state (per-widget) ---
  const fetchedOnce = new WeakSet();     // prevents double result fetches
  const resultsControllers = new WeakMap(); // AbortController per widget

  // --- Utilities ---
  const log = (...args) => { if (DEBUG) console.log("[DEBUG]", ...args); };
  const safePct = (n, d) => (d > 0 ? Math.max(0, Math.min(100, (n / d) * 100)) : 0);
  const randReqId = () => { try { return crypto.randomUUID(); } catch { return String(Math.random()).slice(2); } };
  const $all = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // Safe localStorage helpers (handles Safari private mode)
  function getStored(key) { try { return localStorage.getItem(key); } catch { return null; } }
  function setStored(key, val) { try { localStorage.setItem(key, val); } catch {} }

  // Make a fetch with an AbortController scoped to a widget to prevent overlaps
  function widgetFetch(widget, url, options = {}) {
    // Abort any in-flight request for this widget
    const prev = resultsControllers.get(widget);
    if (prev) prev.abort();

    const controller = new AbortController();
    resultsControllers.set(widget, controller);

    const headers = new Headers(options.headers || {});
    headers.set("X-Request-ID", randReqId());
    // politely hint caches (server should also set no-store)
    headers.set("Cache-Control", "no-store");

    return fetch(url, { ...options, headers, signal: controller.signal });
  }

  // --- Poll widgets ---
  function initializePollWidgets() {
    const pollWidgets = $all(".poll-widget");
    pollWidgets.forEach((widget, index) => {
      // Stash original index for stable re-sorting on the archive page
      if (!widget.dataset.originalIndex) widget.dataset.originalIndex = String(index);

      const billId = widget.dataset.billId;
      if (!billId) return;

      const options = $all(".poll-option", widget);
      const messageContainer = widget.querySelector(".poll-message");

      // If user already voted, just highlight here (fetch happens in bootstrap once)
      const currentVote = getStored(`voted_${billId}`);
      if (currentVote) {
        highlightCurrentVote(options, currentVote);
      }

      // Attach click handlers once
      options.forEach((option) => {
        // guard against duplicate listeners if script accidentally included twice
        if (option.dataset.tcBound === "1") return;
        option.dataset.tcBound = "1";

        option.addEventListener("click", () => {
          const voteType = option.dataset.vote;
          const storedVote = getStored(`voted_${billId}`) || null;

          if (storedVote && voteType === storedVote) {
            // tiny UX nudge
            if (messageContainer) {
              showLoadingMessage(messageContainer, "You already selected this option.");
              setTimeout(() => { messageContainer.style.display = "none"; }, 1200);
            }
            return;
          }

          handleVote(billId, voteType, widget, storedVote);
        }, { passive: true });
      });
    });
  }

  function handleVote(billId, voteType, widget, previousVote) {
    const options = $all(".poll-option", widget);
    const messageContainer = widget.querySelector(".poll-message");

    disablePollOptions(options);
    showLoadingMessage(messageContainer, "Recording your vote...");

    fetch("/api/vote", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Request-ID": randReqId() },
      body: JSON.stringify({
        bill_id: billId,
        vote_type: voteType,
        previous_vote: previousVote || null
      })
    })
    .then(async (response) => {
      let data = {};
      try { data = await response.json(); } catch (_) {}
      if (!response.ok || !data.success) {
        const msg = (data && data.error) ? data.error : `Failed to record vote (HTTP ${response.status})`;
        throw new Error(msg);
      }
      return data;
    })
    .then(() => {
      const isChange = !!previousVote && previousVote !== voteType;
      if (isChange) {
        showSuccessMessage(messageContainer, "Vote changed successfully!");
      } else {
        showSuccessMessage(messageContainer, "Thanks for voting!");
      }

      setStored(`voted_${billId}`, voteType);
      highlightCurrentVote(options, voteType);

      // After vote, refresh results exactly once
      fetchedOnce.delete(widget); // allow a fresh fetch
      fetchOnceResults(billId, widget);
    })
    .catch((error) => {
      console.error("Vote error:", error);
      showErrorMessage(messageContainer, error.message || "Network error. Please try again.");
    })
    .finally(() => {
      enablePollOptions(options);
    });
  }

  function fetchOnceResults(billId, widget) {
    if (fetchedOnce.has(widget)) return;

    fetchedOnce.add(widget);
    fetchAndDisplayResults(billId, widget).catch(() => {
      // if it failed, clear the fetched flag to allow retry on next attempt
      fetchedOnce.delete(widget);
    });
  }

  function fetchAndDisplayResults(billId, widget) {
    const resultsContainer = widget.querySelector(".poll-results");
    const messageContainer = widget.querySelector(".poll-message");

    showLoadingMessage(messageContainer, "Loading results...");

    return widgetFetch(widget, `/api/poll-results/${billId}`)
      .then(async (response) => {
        let data = {};
        try { data = await response.json(); } catch (_) {}
        if (!response.ok || (data && data.error)) {
          const msg = (data && data.error) ? data.error : `Failed to load results (HTTP ${response.status})`;
          throw new Error(msg);
        }
        return data;
      })
      .then((results) => {
        updateResultsDisplay(results, resultsContainer);
        if (resultsContainer) resultsContainer.style.display = "block";
        if (messageContainer) messageContainer.style.display = "none";
      })
      .catch((error) => {
        console.error("Error fetching results:", error);
        showErrorMessage(messageContainer, error.message || "Failed to load results. Please refresh the page.");
        throw error; // propagate to let caller clear fetchedOnce if desired
      });
  }

  function updateResultsDisplay(results, container) {
    if (!container) return;

    const yes = Number(results.yes_votes || 0);
    const no  = Number(results.no_votes  || 0);
    const total = Number(
      (results.total != null ? results.total : (yes + no))
    );

    const yesPercent = safePct(yes, total);
    const noPercent  = safePct(no, total);

    const yesFill = container.querySelector(".yes-fill");
    const noFill  = container.querySelector(".no-fill");

    if (yesFill) yesFill.style.width = `${yesPercent}%`;
    if (noFill) noFill.style.width  = `${noPercent}%`;

    const yesCountEl = yesFill ? yesFill.querySelector(".result-count") : null;
    const noCountEl  = noFill  ? noFill.querySelector(".result-count")  : null;

    if (yesCountEl) yesCountEl.textContent = String(yes);
    if (noCountEl)  noCountEl.textContent  = String(no);

    const totalEl = container.querySelector(".votes-count");
    if (totalEl) totalEl.textContent = String(isFinite(total) ? total : yes + no);
  }

  // Highlight the user's current vote selection
  function highlightCurrentVote(options, currentVote) {
    options.forEach(option => {
      if (option.dataset.vote === currentVote) {
        option.classList.add("selected");
        option.style.cursor = "default";
        option.title = "Your current vote (click another option to change)";
      } else {
        option.classList.remove("selected");
        option.style.cursor = "pointer";
        option.title = "";
      }
    });
  }

  function disablePollOptions(options) {
    options.forEach((option) => {
      option.disabled = true;
      option.style.opacity = "0.6";
      option.style.cursor = "not-allowed";
      option.setAttribute("aria-disabled", "true");
    });
  }

  function enablePollOptions(options) {
    options.forEach((option) => {
      option.disabled = false;
      option.style.opacity = "1";
      option.style.cursor = "pointer";
      option.removeAttribute("aria-disabled");
    });
  }

  function showLoadingMessage(container, message) {
    if (!container) return;
    container.textContent = message;
    container.className = "poll-message";
    container.style.display = "block";
  }

  function showSuccessMessage(container, message) {
    if (!container) return;
    container.textContent = message;
    container.className = "poll-message success";
    container.style.display = "block";
    setTimeout(() => { container.style.display = "none"; }, 3000);
  }

  function showErrorMessage(container, message) {
    if (!container) return;
    container.textContent = message;
    container.className = "poll-message error";
    container.style.display = "block";
  }

  // --- Mobile navigation ---
  function setupMobileNavigation() {
    const navToggle = document.querySelector(".nav-toggle");
    const navMenu   = document.querySelector(".nav-menu");
    if (!navToggle || !navMenu) return;

    if (navToggle.dataset.tcBound === "1") return; // idempotent
    navToggle.dataset.tcBound = "1";

    navToggle.addEventListener("click", (e) => {
      e.stopPropagation();
      const isExpanded = navMenu.classList.contains("active");
      navMenu.classList.toggle("active");
      navToggle.setAttribute("aria-expanded", String(!isExpanded));
      const bars = navToggle.querySelectorAll(".bar");
      bars.forEach((bar) => bar.classList.toggle("active"));
    });

    document.addEventListener("click", (event) => {
      if (!navMenu.classList.contains("active")) return;
      if (!event.target.closest(".nav-menu") && !event.target.closest(".nav-toggle")) {
        navMenu.classList.remove("active");
        navToggle.setAttribute("aria-expanded", "false");
        const bars = navToggle.querySelectorAll(".bar");
        bars.forEach((bar) => bar.classList.remove("active"));
      }
    }, { passive: true });

    const navLinks = navMenu.querySelectorAll(".nav-link");
    navLinks.forEach((link) => {
      if (link.dataset.tcBound === "1") return;
      link.dataset.tcBound = "1";
      link.addEventListener("click", () => {
        navMenu.classList.remove("active");
        navToggle.setAttribute("aria-expanded", "false");
        const bars = navToggle.querySelectorAll(".bar");
        bars.forEach((bar) => bar.classList.remove("active"));
      }, { passive: true });
    });
  }

  // --- Archive mini-results bars ---
  function initArchiveMiniResults() {
    const containers = $all(".mini-results");
    containers.forEach((c) => {
      const yes = parseFloat(c.dataset.yes || "0");
      const no  = parseFloat(c.dataset.no  || "0");
      const yesEl = c.querySelector(".mini-result.yes");
      const noEl  = c.querySelector(".mini-result.no");
      if (yesEl && isFinite(yes)) yesEl.style.width = `${Math.max(0, Math.min(100, yes))}%`;
      if (noEl  && isFinite(no))  noEl.style.width  = `${Math.max(0, Math.min(100, no))}%`;
    });
  }

  // --- Archive filtering and sorting ---
  function initializeBillFiltering() {
    const filterSelect = document.getElementById("status-filter");
    const sortCheckbox = document.getElementById("sort-by-impact");
    if (!filterSelect) return; // not on archive page

    const urlParams = new URLSearchParams(window.location.search);
    const urlStatus = urlParams.get("status");
    if (urlStatus) filterSelect.value = urlStatus;

    if (filterSelect.dataset.tcBound !== "1") {
      filterSelect.dataset.tcBound = "1";
      filterSelect.addEventListener("change", function () {
        const selectedStatus = this.value;
        setStored("archive_filter", selectedStatus);

        const newUrl = new URL(window.location.href);
        if (selectedStatus === "all") {
          newUrl.searchParams.delete("status");
        } else {
          newUrl.searchParams.set("status", selectedStatus);
        }
        newUrl.searchParams.delete("page"); // reset pagination
        window.location.href = newUrl.toString();
      });
    }

    if (sortCheckbox && sortCheckbox.dataset.tcBound !== "1") {
      sortCheckbox.dataset.tcBound = "1";
      sortCheckbox.addEventListener("change", function () {
        sortBillsByTeenImpact(this.checked);
      }, { passive: true });
    }
  }

  function sortBillsByTeenImpact(sortEnabled) {
    const billsGrid = document.querySelector(".bills-grid");
    if (!billsGrid) return;

    const billCards = Array.from(billsGrid.querySelectorAll(".bill-card"));
    if (billCards.length === 0) return;

    if (sortEnabled) {
      billCards.sort((a, b) => {
        const scoreA = parseFloat(a.dataset.teenImpact) || -1;
        const scoreB = parseFloat(b.dataset.teenImpact) || -1;
        if (scoreA === -1 && scoreB === -1) return 0;
        if (scoreA === -1) return 1;
        if (scoreB === -1) return -1;
        return scoreB - scoreA;
      });
    } else {
      billCards.sort((a, b) => {
        const indexA = parseInt(a.dataset.originalIndex || "0", 10);
        const indexB = parseInt(b.dataset.originalIndex || "0", 10);
        return indexA - indexB;
      });
    }

    // Re-append in order
    const frag = document.createDocumentFragment();
    billCards.forEach((card) => frag.appendChild(card));
    billsGrid.innerHTML = "";
    billsGrid.appendChild(frag);
  }

  // --- Helpers ---
  function debounce(func, wait) {
    let timeout;
    return function (...args) {
      clearTimeout(timeout);
      timeout = setTimeout(() => func.apply(this, args), wait);
    };
  }

  // Close mobile menu on resize to larger screens
  const onResize = debounce(() => {
    const navMenu = document.querySelector(".nav-menu");
    const navToggle = document.querySelector(".nav-toggle");
    if (window.innerWidth > 768 && navMenu && navMenu.classList.contains("active")) {
      navMenu.classList.remove("active");
      if (navToggle) {
        navToggle.setAttribute("aria-expanded", "false");
        const bars = navToggle.querySelectorAll(".bar");
        bars.forEach((bar) => bar.classList.remove("active"));
      }
    }
  }, 250);

  // --- One-time bootstrap ---
  let bootstrapped = false;
  function bootstrap() {
    if (bootstrapped) return; // idempotent if script gets included twice
    bootstrapped = true;

    initializePollWidgets();
    setupMobileNavigation();
    initArchiveMiniResults();
    initializeBillFiltering();

    // Fetch results once per widget if user has a stored vote
    const pollWidgets = $all(".poll-widget");
    pollWidgets.forEach((widget) => {
      const billId = widget.dataset.billId;
      if (!billId) return;

      const currentVote = getStored(`voted_${billId}`);
      if (currentVote) {
        const resultsContainer = widget.querySelector(".poll-results");
        if (resultsContainer) resultsContainer.style.display = "block";
        // single source of truth: fetch here only
        fetchOnceResults(billId, widget);
      }
    });

    window.addEventListener("resize", onResize, { passive: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap, { once: true });
  } else {
    // already ready
    bootstrap();
  }

  // Optionally expose a tiny API for testing
  window.TeenCivics = Object.assign(window.TeenCivics || {}, {
    _debug: { fetchedOnce, resultsControllers },
    refreshResultsForAll: () => {
      $all(".poll-widget").forEach((w) => {
        const billId = w.dataset.billId;
        if (!billId) return;
        fetchedOnce.delete(w);
        fetchOnceResults(billId, w);
      });
    }
  });
})();
