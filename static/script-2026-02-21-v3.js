// TeenCivics JavaScript - Poll Voting, UI Interactions, and Archive Utilities
// Optimized to avoid duplicate /api/poll-results calls and reduce redundant work.

(() => {
  "use strict";

  // --- Config ---
  const DEBUG = false;
  const API_BASE = (window.APP_ROOT || (window.location.pathname || "").startsWith("/beta") ? "/beta" : "");

  // --- Internal state (per-widget) ---
  const fetchedOnce = new WeakSet();     // prevents double result fetches
  const resultsControllers = new WeakMap(); // AbortController per widget

  // --- Utilities ---
  const log = (...args) => { if (DEBUG) console.log("[DEBUG]", ...args); };
  const safePct = (n, d) => (d > 0 ? Math.max(0, Math.min(100, (n / d) * 100)) : 0);
  const randReqId = () => { try { return crypto.randomUUID(); } catch { return String(Math.random()).slice(2); } };
  const $all = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // Apply a user-stats object (same shape as /api/me) to every
  // data-rail-* element on the page. Both the navbar pill and the
  // right-side rail bind to these attributes.
  function applyUserStats(me) {
    if (!me) return;
    document.querySelectorAll("[data-rail-tier]").forEach((el) => { el.textContent = me.tier; });
    document.querySelectorAll("[data-rail-balance]").forEach((el) => { el.textContent = String(Math.round(me.balance)); });
    document.querySelectorAll("[data-rail-lifetime]").forEach((el) => { el.textContent = String(me.lifetime_votes_cast); });
    document.querySelectorAll("[data-rail-daily]").forEach((el) => { el.textContent = `${me.daily_used}/${me.daily_cap}`; });
    document.querySelectorAll("[data-rail-fill]").forEach((el) => {
      if (me.progress) el.style.width = me.progress.percent + "%";
    });
    document.querySelectorAll("[data-rail-to-next]").forEach((el) => {
      if (me.progress && me.progress.votes_to_next != null) {
        el.textContent = String(Math.round(me.progress.votes_to_next));
      }
    });
    document.querySelectorAll("[data-rail-next-tier]").forEach((el) => {
      if (me.progress && me.progress.next_tier) el.textContent = me.progress.next_tier;
    });
    document.querySelectorAll("[data-rail-tell-rep-lifetime]").forEach((el) => {
      if (me.lifetime_stances_sent != null) el.textContent = String(me.lifetime_stances_sent);
    });
    document.querySelectorAll("[data-rail-tell-rep-daily]").forEach((el) => {
      if (me.daily_tell_rep_used != null && me.daily_tell_rep_cap != null) {
        el.textContent = `${me.daily_tell_rep_used}/${me.daily_tell_rep_cap}`;
      }
    });
  }

  // Fallback path: fetch fresh stats from /api/me. Used when we don't
  // already have updated stats from a recent action response.
  function refreshUserRail() {
    const hasPill = document.querySelector(".nav-user");
    const hasRail = document.querySelector("[data-user-rail]");
    if (!hasPill && !hasRail) return;

    fetch(API_BASE + "/api/me", { headers: { "Cache-Control": "no-store" } })
      .then((r) => r.ok ? r.json() : Promise.reject())
      .then((me) => {
        if (!me || !me.authenticated) return;
        applyUserStats(me);
      })
      .catch(() => {});
  }

  // Read the per-page CSRF token from the <meta name="csrf-token"> tag
  // (set in base.html). Returns "" if missing — server will reject the
  // request, which is the correct behavior. Sent as X-CSRFToken on all
  // state-changing POSTs.
  function getCsrfToken() {
    const el = document.querySelector('meta[name="csrf-token"]');
    return el ? (el.getAttribute("content") || "") : "";
  }

  // Expose for the tell-rep script (separate IIFE) to award bonus Votes.
  window.TC = window.TC || {};
  window.TC.applyUserStats = applyUserStats;
  window.TC.getCsrfToken = getCsrfToken;
  window.TC.API_BASE = API_BASE;

  // Safe localStorage helpers (handles Safari private mode)
  function getStored(key) { try { return localStorage.getItem(key); } catch { return null; } }
  function setStored(key, val) { try { localStorage.setItem(key, val); } catch {} }

  // One-shot cookie sweep on logout: the /logout endpoint sets
  // clear_local_vote_cache=1 (max-age 60s, non-HttpOnly) so we can
  // detect it client-side and remove all `voted_*` localStorage
  // entries — otherwise a signed-out user keeps seeing their old
  // "voted yes" highlights from before they logged out, which feels
  // like a privacy bleed even though the data is technically theirs.
  //
  // We also set a session-scoped sessionStorage flag `suppress_vote_sync`
  // that prevents the bootstrap from immediately re-hydrating localStorage
  // from /api/my-votes (which is keyed by the voter_id cookie that
  // intentionally PERSISTS past logout — needed so anon votes still
  // attach to a future account on signup). The flag clears when the
  // browser tab closes OR when the user signs back in.
  function maybeClearVoteCacheOnLogout() {
    if (!document.cookie.split("; ").some(c => c.startsWith("clear_local_vote_cache="))) return;
    try {
      const keysToRemove = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.startsWith("voted_")) keysToRemove.push(k);
      }
      keysToRemove.forEach(k => { try { localStorage.removeItem(k); } catch {} });
    } catch {}
    try { sessionStorage.setItem("suppress_vote_sync", "1"); } catch {}
    // Delete the marker cookie so subsequent loads don't keep clearing.
    document.cookie = "clear_local_vote_cache=; Max-Age=0; Path=/; SameSite=Lax";
  }
  maybeClearVoteCacheOnLogout();

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

  // --- Sponsor Reveal ---
  // Reveals sponsor information after user has voted on a bill
  function checkAndRevealSponsor(billId) {
    const voted = getStored(`voted_${billId}`);
    const sponsorEl = document.getElementById(`sponsor-reveal-${billId}`);
    
    if (voted && sponsorEl) {
      sponsorEl.style.display = 'block';
    }
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
        checkAndRevealSponsor(billId);  // Reveal sponsor if already voted
        // Show Tell Your Rep button (handles race condition with DOMContentLoaded)
        if (window.TeenCivics && window.TeenCivics.showTellRepButton) {
          window.TeenCivics.showTellRepButton(billId);
        }
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
            // Still show Tell Your Rep button in case it wasn't visible
            if (window.TeenCivics && window.TeenCivics.showTellRepButton) {
              window.TeenCivics.showTellRepButton(billId);
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

    fetch(API_BASE + "/api/vote", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": randReqId(),
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({
        bill_id: billId,
        vote_type: voteType,
        previous_vote: previousVote || null,
        // Used only when the server bounces this request with 401
        // auth_required — it tells /login where to send the user back.
        return_to: window.location.pathname + window.location.search
      })
    })
    .then(async (response) => {
      let data = {};
      try { data = await response.json(); } catch (_) {}
      // Soft-wall: voting requires an account. Server returns 401 with a
      // contextual login URL that bounces the user back to this bill after
      // sign-in. Hard redirect — no inline error, the login page explains.
      // Re-enable the widget first so the bfcache snapshot is the clean
      // pre-click state, not the "Recording your vote..." disabled state.
      // Without this, hitting back after the redirect restores a frozen UI.
      if (response.status === 401 && data && data.error === "auth_required" && data.login_url) {
        enablePollOptions(options);
        if (messageContainer) messageContainer.style.display = "none";
        window.location.href = data.login_url;
        return new Promise(() => {}); // Block subsequent .then() during nav
      }
      if (!response.ok || !data.success) {
        const msg = (data && data.error) ? data.error : `Failed to record vote (HTTP ${response.status})`;
        throw new Error(msg);
      }
      return data;
    })
    .then((data) => {
      const isChange = !!previousVote && previousVote !== voteType;
      if (isChange) {
        showSuccessMessage(messageContainer, "Vote changed successfully!");
      } else {
        showSuccessMessage(messageContainer, "Thanks for voting!");
      }

      setStored(`voted_${billId}`, voteType);
      highlightCurrentVote(options, voteType);

      // Optimistic local poll update — apply the delta from this vote to
      // the displayed bars immediately, before the /api/poll-results
      // round-trip returns. The server is already consistent (S1 fix),
      // and the followup fetch corrects any drift.
      applyOptimisticVoteDelta(widget, voteType, previousVote);

      // Update pill/rail directly from the vote response — saves a
      // round-trip to /api/me. Fall back to refetching if the response
      // didn't include user stats (anonymous voter).
      if (data && data.user) {
        applyUserStats(data.user);
      } else {
        refreshUserRail();
      }

      // Pre-warm reasoning cache in background (don't await, don't block UI)
      fetch(API_BASE + '/api/pre-generate-reasoning', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify({ bill_id: billId, vote: voteType })
      }).catch(() => {}); // Silently ignore failures

      // Reveal sponsor after voting
      checkAndRevealSponsor(billId);

      // Show Tell Your Rep button (if tell-rep.js is loaded)
      if (window.TeenCivics && window.TeenCivics.showTellRepButton) {
        window.TeenCivics.showTellRepButton(billId);
      }

      // If vote was changed, notify Tell Your Rep to regenerate the email
      if (isChange && window.TeenCivics && window.TeenCivics.onVoteChanged) {
        window.TeenCivics.onVoteChanged(billId, voteType);
      }

      // Record the vote in sessionStorage so that if the user navigates
      // to another page (e.g. /bills archive) within this tab, the archive
      // can apply the same optimistic delta to its mini-results — no need
      // to wait for the next SSR snapshot.
      try {
        const stash = JSON.parse(sessionStorage.getItem("pendingVoteDeltas") || "{}");
        stash[billId] = { voteType: voteType, previousVote: previousVote || null, ts: Date.now() };
        sessionStorage.setItem("pendingVoteDeltas", JSON.stringify(stash));
      } catch (_) {}

      // Confirm/correct against server (this also catches any concurrent votes
      // from other users that landed between optimistic-update and now)
      fetchedOnce.delete(widget);
      fetchOnceResults(billId, widget);

      // Restart live polling so other voters' votes appear in real time
      restartLivePollRefresh();
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

    return widgetFetch(widget, API_BASE + `/api/poll-results/${billId}`)
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
    // Compute total from the parts we render to avoid backend mismatches
    const total = yes + no;

    const yesPercent = safePct(yes, total);
    const noPercent  = safePct(no, total);
    
    // Debug: compare backend total vs computed denominator for bars
    log && log("Poll calc", { yes, no, total, backendTotal: results.total });

    const yesFill = container.querySelector(".yes-fill");
    const noFill  = container.querySelector(".no-fill");

    // Ensure we update both width and visibility for proper display
    if (yesFill) {
      yesFill.style.width = `${yesPercent}%`;
      // Ensure the element is visible even when width is 0%
      yesFill.style.display = 'flex';
    }
    if (noFill) {
      noFill.style.width = `${noPercent}%`;
      // Ensure the element is visible even when width is 0%
      noFill.style.display = 'flex';
    }

    const yesCountEl = yesFill ? yesFill.querySelector(".result-count") : null;
    const noCountEl  = noFill  ? noFill.querySelector(".result-count")  : null;

    if (yesCountEl) yesCountEl.textContent = String(yes);
    if (noCountEl)  noCountEl.textContent  = String(no);

    const totalEl = container.querySelector(".votes-count");
    if (totalEl) totalEl.textContent = String(isFinite(total) ? total : yes + no);
    
    // Force reflow to ensure the changes are rendered properly
    if (yesFill) yesFill.offsetHeight;
    if (noFill) noFill.offsetHeight;
  }

  // Apply the just-voted delta to the on-screen poll bars immediately,
  // before the /api/poll-results round-trip returns. Reads current
  // displayed counts (from the .result-count spans we render to) and
  // increments/decrements based on what changed.
  function applyOptimisticVoteDelta(widget, voteType, previousVote) {
    if (!widget) return;
    const resultsContainer = widget.querySelector(".poll-results");
    if (!resultsContainer) return;

    // Read current displayed counts. If nothing's rendered yet (first
    // vote on a fresh bill), default to 0 and let the followup fetch
    // populate.
    const yesEl = resultsContainer.querySelector(".yes-fill .result-count");
    const noEl  = resultsContainer.querySelector(".no-fill .result-count");
    let yes = parseInt(yesEl ? yesEl.textContent : "0", 10) || 0;
    let no  = parseInt(noEl  ? noEl.textContent  : "0", 10) || 0;

    // Subtract previous vote (if any) first, then add new vote
    if (previousVote === "yes") yes = Math.max(0, yes - 1);
    if (previousVote === "no")  no  = Math.max(0, no - 1);
    if (voteType === "yes") yes += 1;
    if (voteType === "no")  no  += 1;

    updateResultsDisplay({ yes_votes: yes, no_votes: no, total: yes + no }, resultsContainer);

    // Ensure the results section is visible — on first vote it may be hidden
    if (resultsContainer.style.display === "none") {
      resultsContainer.style.display = "block";
    }
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

  // Apply a pending vote delta to an archive .poll-preview that was SSR'd
  // with stale counts (because the vote happened after the page was
  // rendered). Updates the data-* attrs, the --yes-width/--no-width CSS
  // vars, the percentage spans, and the total-votes caption.
  function applyArchivePollDelta(preview, voteType, previousVote) {
    if (!preview) return;
    let yes = parseInt(preview.dataset.yesCount || "0", 10) || 0;
    let no  = parseInt(preview.dataset.noCount  || "0", 10) || 0;

    if (previousVote === "yes") yes = Math.max(0, yes - 1);
    if (previousVote === "no")  no  = Math.max(0, no - 1);
    if (voteType === "yes") yes += 1;
    if (voteType === "no")  no  += 1;

    preview.dataset.yesCount = String(yes);
    preview.dataset.noCount  = String(no);

    const total = yes + no;
    const yesPct = total > 0 ? Math.round((yes / total) * 1000) / 10 : 0;
    const noPct  = total > 0 ? Math.round((no  / total) * 1000) / 10 : 0;

    const content = preview.querySelector(".poll-results-content");
    if (content) {
      content.style.setProperty("--yes-width", `${yesPct}%`);
      content.style.setProperty("--no-width",  `${noPct}%`);
    }

    const yesPctEl = preview.querySelector('.poll-option[data-vote="yes"] .poll-percentage');
    const noPctEl  = preview.querySelector('.poll-option[data-vote="no"]  .poll-percentage');
    if (yesPctEl) yesPctEl.textContent = `${yesPct}%`;
    if (noPctEl)  noPctEl.textContent  = `${noPct}%`;

    const totalEl = preview.querySelector(".poll-total");
    if (totalEl) {
      totalEl.textContent = `${total} total vote${total !== 1 ? "s" : ""}`;
    }
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

  // --- Archive poll preview vote-to-unlock ---
  // Shows/hides poll results based on whether user has voted on each bill.
  // Also applies any pending vote deltas from sessionStorage so a vote
  // cast on one page reflects on the archive without waiting for the
  // next SSR snapshot.
  function initArchiveVoteToUnlock() {
    // Pull pending vote deltas the user cast on another page in this tab.
    // We don't have the SSR yes/no counts for those bills here, but the
    // server-side rendered .mini-results dataset has them. Use that.
    let pendingDeltas = {};
    try {
      pendingDeltas = JSON.parse(sessionStorage.getItem("pendingVoteDeltas") || "{}");
    } catch (_) {}

    const pollPreviews = $all(".poll-preview[data-bill-id]");
    pollPreviews.forEach((preview) => {
      const billId = preview.dataset.billId;
      if (!billId) return;

      const overlay = preview.querySelector(".vote-to-unlock-overlay");
      const resultsContent = preview.querySelector(".poll-results-content");

      if (!overlay || !resultsContent) return;

      // Apply pending delta to the SSR-rendered widths + percentages
      // so the bars reflect the freshly-cast vote.
      const pending = pendingDeltas[billId];
      if (pending) {
        applyArchivePollDelta(preview, pending.voteType, pending.previousVote);
      }

      const hasVoted = getStored(`voted_${billId}`);
      const badge = preview.querySelector(".your-vote-badge");
      if (hasVoted) {
        // User has voted - show results, hide overlay
        overlay.style.display = "none";
        resultsContent.style.display = "block";
        // Populate the heading-level "you voted X" badge — sits in the
        // poll header, color-coded yes/no, instead of floating between bars.
        if (badge) {
          const label = hasVoted === "yes" ? "Voted Yes"
                       : hasVoted === "no" ? "Voted No"
                       : "Voted Unsure";
          badge.textContent = "✓ " + label;
          badge.dataset.vote = hasVoted;
          badge.hidden = false;
        }
      } else {
        // User has not voted - show overlay, hide results
        overlay.style.display = "flex";
        resultsContent.style.display = "none";
        if (badge) {
          badge.hidden = true;
          badge.textContent = "";
          delete badge.dataset.vote;
        }
      }
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

  // --- Server vote sync ---
  // Restores votes from the server (via voter_id cookie) into localStorage.
  // This ensures that if localStorage was cleared, previously recorded votes
  // are restored before poll widgets initialize.
  //
  // EXCEPTION: if the user just logged out, sessionStorage carries a
  // `suppress_vote_sync` flag. We honor it for the current tab/session so
  // a logged-out user doesn't see their previously-voted highlights
  // re-hydrate from the persistent voter_id cookie. The flag is cleared
  // by /api/me when the response indicates an authenticated session
  // (re-login) OR naturally when the tab closes.
  async function syncVotesFromServer() {
    try {
      const suppressed = sessionStorage.getItem("suppress_vote_sync") === "1";
      // If suppressed, check whether the user has signed back in (in which
      // case we clear the flag and proceed — they're not logged out anymore).
      if (suppressed) {
        try {
          const meResp = await fetch(API_BASE + "/api/me", {
            credentials: "same-origin",
            headers: { "Cache-Control": "no-store" }
          });
          if (meResp.ok) {
            const me = await meResp.json();
            if (me && me.authenticated) {
              sessionStorage.removeItem("suppress_vote_sync");
            } else {
              log("syncVotesFromServer: suppressed (post-logout)");
              return;
            }
          } else {
            return;
          }
        } catch {
          return;
        }
      }

      const response = await fetch(API_BASE + "/api/my-votes", {
        credentials: "same-origin",           // send voter_id cookie
        headers: { "Cache-Control": "no-store" }
      });
      if (!response.ok) return;               // silently skip on HTTP errors

      const data = await response.json();
      const votes = data && data.votes;
      if (!votes || typeof votes !== "object") return;

      for (const [billId, voteType] of Object.entries(votes)) {
        // Only backfill — never overwrite an existing localStorage vote
        if (!getStored("voted_" + billId)) {
          setStored("voted_" + billId, voteType);
          log("syncVotesFromServer: restored", billId, "→", voteType);
        }
      }
    } catch (_) {
      // Network error, CORS issue, JSON parse failure, etc.
      // Proceed silently — localStorage-only behaviour is the fallback.
    }
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
  async function bootstrap() {
    if (bootstrapped) return; // idempotent if script gets included twice
    bootstrapped = true;

    // Restore any server-side votes into localStorage before initialising widgets.
    // This is fault-tolerant: if the request fails, we proceed with localStorage only.
    await syncVotesFromServer();

    initializePollWidgets();
    setupMobileNavigation();
    initArchiveMiniResults();
    initArchiveVoteToUnlock();
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

  // bfcache restore: when the user hits Back after being redirected to /login,
  // Safari/Chrome restore the DOM exactly as it was — buttons disabled, "Recording
  // your vote..." still shown. Reset every poll widget so the page is interactive
  // again. event.persisted === true means the page came from bfcache.
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    $all(".poll-widget").forEach((widget) => {
      const options = $all(".poll-option", widget);
      const messageContainer = widget.querySelector(".poll-message");
      enablePollOptions(options);
      if (messageContainer) messageContainer.style.display = "none";
    });
  });

  // --- Share Dropdown ---
  function initializeShareDropdowns() {
    const shareDropdowns = $all(".share-dropdown");
    
    shareDropdowns.forEach((dropdown) => {
      const button = dropdown.querySelector(".btn-share");
      const options = dropdown.querySelector(".share-options");
      const copyBtn = dropdown.querySelector(".share-copy");
      
      if (!button || !options) return;
      
      // Toggle dropdown on button click
      button.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = options.classList.contains("show");
        
        // Close all other dropdowns first
        $all(".share-options.show").forEach((o) => {
          o.classList.remove("show");
          o.closest(".share-dropdown")?.querySelector(".btn-share")?.setAttribute("aria-expanded", "false");
        });
        
        if (!isOpen) {
          options.classList.add("show");
          button.setAttribute("aria-expanded", "true");
        }
      }, { passive: false });
      
      // Copy link functionality
      if (copyBtn) {
        copyBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const textToCopy = copyBtn.dataset.copyText || copyBtn.dataset.url || window.location.href;
          const originalText = copyBtn.textContent;

          try {
            await navigator.clipboard.writeText(textToCopy);
            copyBtn.textContent = "✓ Copied!";
            copyBtn.classList.add("copied");

            setTimeout(() => {
              copyBtn.textContent = originalText;
              copyBtn.classList.remove("copied");
              options.classList.remove("show");
              button.setAttribute("aria-expanded", "false");
            }, 1500);
          } catch (err) {
            console.error("Failed to copy:", err);
            // Fallback: select and copy
            const textArea = document.createElement("textarea");
            textArea.value = textToCopy;
            textArea.style.position = "fixed";
            textArea.style.opacity = "0";
            document.body.appendChild(textArea);
            textArea.select();
            try {
              document.execCommand("copy");
              copyBtn.textContent = "✓ Copied!";
              copyBtn.classList.add("copied");
              setTimeout(() => {
                copyBtn.textContent = originalText;
                copyBtn.classList.remove("copied");
                options.classList.remove("show");
                button.setAttribute("aria-expanded", "false");
              }, 1500);
            } catch (e2) {
              // Lucide x-circle inline — matches the Python icon('x-circle')
              copyBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide-icon" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg> Failed';
              setTimeout(() => {
                copyBtn.textContent = originalText;
                button.setAttribute("aria-expanded", "false");
              }, 1500);
            }
            document.body.removeChild(textArea);
          }
        }, { passive: false });
      }
    });
    
    // Close dropdown when clicking outside
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".share-dropdown")) {
        $all(".share-options.show").forEach((o) => {
          o.classList.remove("show");
          o.closest(".share-dropdown")?.querySelector(".btn-share")?.setAttribute("aria-expanded", "false");
        });
      }
    }, { passive: true });
    
    // Close on Escape key
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        $all(".share-options.show").forEach((o) => {
          o.classList.remove("show");
          o.closest(".share-dropdown")?.querySelector(".btn-share")?.setAttribute("aria-expanded", "false");
        });
      }
    }, { passive: true });
  }

  // Add share dropdown init to bootstrap
  initializeShareDropdowns();

  // --- Live poll refresh (real-time updates from other voters) ---
  const LIVE_POLL_INTERVAL_MS = 15000; // 15 seconds — balances "feels live" with API cost
  let livePollTimer = null;

  function startLivePollRefresh() {
    if (livePollTimer) return; // already running

    // Works on both bill detail and archive pages
    const widgets = $all(".poll-widget");
    if (widgets.length === 0) return;

    livePollTimer = setInterval(() => {
      // Pause when tab is hidden to save bandwidth
      if (document.visibilityState === "hidden") return;

      widgets.forEach((widget) => {
        const billId = widget.dataset.billId;
        if (!billId) return;
        // Only refresh if user has voted (results are visible)
        if (!getStored(`voted_${billId}`)) return;

        const resultsContainer = widget.querySelector(".poll-results");
        if (!resultsContainer || resultsContainer.style.display === "none") return;

        // Silently fetch fresh results and update the bars
        fetch(API_BASE + `/api/poll-results/${billId}`, {
          headers: { "Cache-Control": "no-store" }
        })
        .then((r) => r.ok ? r.json() : Promise.reject())
        .then((results) => updateResultsDisplay(results, resultsContainer))
        .catch(() => {}); // silently ignore errors
      });
    }, LIVE_POLL_INTERVAL_MS);
  }

  function stopLivePollRefresh() {
    if (livePollTimer) {
      clearInterval(livePollTimer);
      livePollTimer = null;
    }
  }

  // Restart the live poll timer so the next tick happens in LIVE_POLL_INTERVAL_MS
  // from NOW (called after a vote so the user's results are immediately fresh).
  function restartLivePollRefresh() {
    stopLivePollRefresh();
    startLivePollRefresh();
  }

  // Start/stop live refresh based on tab visibility
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && !livePollTimer) {
      startLivePollRefresh();
    }
  }, { passive: true });

  // Start live polling after bootstrap completes
  setTimeout(startLivePollRefresh, 2000);

  // --- Split pill → toggle user-rail ---
  (function initPillRailToggle() {
    const btn = document.getElementById("user-pill-btn");
    const rail = document.getElementById("user-rail");
    if (!btn || !rail) return;

    function open() {
      rail.hidden = false;
      btn.setAttribute("aria-expanded", "true");
    }

    function close() {
      rail.hidden = true;
      btn.setAttribute("aria-expanded", "false");
    }

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      rail.hidden ? open() : close();
    });

    // Close when clicking outside the pill or rail
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".nav-user") && !e.target.closest("#user-rail")) {
        close();
      }
    }, { passive: true });

    // Close on Escape
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
    }, { passive: true });
  })();

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
    },
    stopLivePollRefresh,
    startLivePollRefresh,
    restartLivePollRefresh,
  });
})();
