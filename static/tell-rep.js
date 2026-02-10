// TeenCivics — Tell Your Rep Module
// Post-vote email flow: ZIP → district → representative → email draft
// IIFE pattern matching existing script.js

(() => {
  "use strict";

  // --- Feature Flag: Localhost Only ---
  const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
  
  if (isLocalhost) {
    // Determine which bills are present and unhide their containers
    const containers = document.querySelectorAll('.tell-rep-container');
    containers.forEach(container => {
      container.style.display = 'block';
    });
    console.log("Tell Your Rep feature enabled (localhost mode)");
  } else {
    // Expose a no-op API so other scripts don't crash and exit
    window.TeenCivics = Object.assign(window.TeenCivics || {}, {
      showTellRepButton: () => {}, // No-op
      onVoteChanged: () => {},     // No-op
    });
    console.log("Tell Your Rep feature disabled (production mode)");
    return;
  }

  // --- Helpers ---
  const $ = (sel, root = document) => root.querySelector(sel);
  const $all = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const randReqId = () => {
    try { return crypto.randomUUID(); } catch { return String(Math.random()).slice(2); }
  };

  // Safe localStorage helpers (Safari private mode)
  function getStored(key) { try { return localStorage.getItem(key); } catch { return null; } }
  function setStored(key, val) { try { localStorage.setItem(key, val); } catch {} }

  // --- Toast Notification ---
  let toastEl = null;
  let toastTimer = null;

  function showToast(message) {
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.className = "copy-toast";
      document.body.appendChild(toastEl);
    }
    toastEl.innerHTML = `<span>✓</span> ${_escHtml(message)}`;
    toastEl.classList.add("show");

    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastEl.classList.remove("show");
    }, 2200);
  }

  // Minimal HTML escape
  function _escHtml(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  // --- In-memory state for vote-change updates ---
  const repContextByBill = new Map();

  // --- Main: Show the Tell Your Rep button after voting ---

  /**
   * Called from script.js after a successful vote.
   * Reveals the "Tell Your Rep" trigger button with a slide-in animation.
   */
  function showTellRepButton(billId) {
    const trigger = document.getElementById(`tell-rep-trigger-${billId}`);
    if (!trigger) return;

    // Small delay so the sponsor reveal plays first
    setTimeout(() => {
      // Show element first (display: none → block), then animate on next frame
      trigger.style.display = "block";
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          trigger.classList.add("visible");
        });
      });
    }, 600);
  }

  /**
   * On page load, check if user already voted on this bill and show the trigger.
   */
  function checkExistingVoteForTellRep() {
    const widgets = $all(".poll-widget");
    widgets.forEach((widget) => {
      const billId = widget.dataset.billId;
      if (!billId) return;
      const voted = getStored(`voted_${billId}`);
      if (voted) {
        showTellRepButton(billId);
      }
    });
  }

  // --- Toggle Section Expand ---
  function initTellRepToggles() {
    const triggers = $all(".btn-tell-rep");
    triggers.forEach((btn) => {
      if (btn.dataset.trBound === "1") return;
      btn.dataset.trBound = "1";

      btn.addEventListener("click", () => {
        const billId = btn.dataset.billId;
        const section = document.getElementById(`tell-rep-section-${billId}`);
        if (!section) return;

        const isExpanded = section.classList.contains("expanded");
        if (isExpanded) {
          section.classList.remove("expanded");
          btn.setAttribute("aria-expanded", "false");
        } else {
          section.classList.add("expanded");
          btn.setAttribute("aria-expanded", "true");
          // Focus the ZIP input
          const zipInput = $(".zip-input", section);
          if (zipInput) setTimeout(() => zipInput.focus(), 400);
        }
      });
    });
  }

  // --- ZIP Input Validation ---
  function initZipValidation() {
    const zipInputs = $all(".zip-input");
    zipInputs.forEach((input) => {
      if (input.dataset.trBound === "1") return;
      input.dataset.trBound = "1";

      // Numeric only
      input.addEventListener("input", () => {
        input.value = input.value.replace(/\D/g, "").slice(0, 5);
        updateZipValidationIcon(input);
      });

      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          const section = input.closest(".tell-rep-section");
          const findBtn = $(".btn-find-rep", section);
          if (findBtn && !findBtn.disabled) findBtn.click();
        }
      });
    });
  }

  function updateZipValidationIcon(input) {
    const wrapper = input.closest(".zip-input-wrapper");
    if (!wrapper) return;
    const icon = $(".zip-validation-icon", wrapper);
    if (!icon) return;

    const val = input.value.trim();
    if (val.length === 0) {
      icon.classList.remove("show", "valid", "invalid");
      input.classList.remove("valid", "invalid");
    } else if (val.length === 5 && /^\d{5}$/.test(val)) {
      icon.textContent = "✓";
      icon.classList.add("show", "valid");
      icon.classList.remove("invalid");
      input.classList.add("valid");
      input.classList.remove("invalid");
    } else {
      icon.textContent = "✗";
      icon.classList.add("show", "invalid");
      icon.classList.remove("valid");
      input.classList.add("invalid");
      input.classList.remove("valid");
    }
  }

  // --- Find My Rep Button ---
  function initFindRepButtons() {
    const buttons = $all(".btn-find-rep");
    buttons.forEach((btn) => {
      if (btn.dataset.trBound === "1") return;
      btn.dataset.trBound = "1";

      btn.addEventListener("click", () => {
        const section = btn.closest(".tell-rep-section");
        if (!section) return;
        const billId = section.dataset.billId;
        const zipInput = $(".zip-input", section);
        const zip = zipInput ? zipInput.value.trim() : "";

        if (!/^\d{5}$/.test(zip)) {
          showSectionError(section, "Please enter a valid 5-digit ZIP code.");
          if (zipInput) zipInput.focus();
          return;
        }

        handleZipSubmit(section, billId, zip);
      });
    });
  }

  // --- Core Flow: ZIP → Districts → Reps → Email ---

  async function handleZipSubmit(section, billId, zip) {
    const resultsArea = $(".tell-rep-results", section);
    const loadingArea = $(".tell-rep-loading", section);
    const errorArea = $(".tell-rep-error", section);
    const findBtn = $(".btn-find-rep", section);

    // Reset
    hideSectionError(section);
    if (resultsArea) resultsArea.innerHTML = "";
    if (resultsArea) resultsArea.style.display = "none";
    if (loadingArea) loadingArea.style.display = "flex";
    if (findBtn) { findBtn.disabled = true; findBtn.textContent = "Looking up…"; }

    try {
      // Step 1: ZIP → districts
      const zipResp = await fetch("/api/zip-lookup", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": randReqId(),
        },
        body: JSON.stringify({ zip }),
      });
      const zipData = await zipResp.json();
      if (!zipResp.ok || zipData.error) {
        throw new Error(zipData.error || "Failed to look up ZIP code.");
      }

      const districts = zipData.districts || [];
      if (districts.length === 0) {
        throw new Error("No congressional district found for this ZIP code.");
      }

      // Step 2: Look up representative for each district
      const reps = [];
      for (const dist of districts) {
        try {
          const repResp = await fetch("/api/rep-lookup", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Request-ID": randReqId(),
            },
            body: JSON.stringify({ state: dist.state, district: dist.district }),
          });
          const repData = await repResp.json();
          if (repResp.ok && repData.found) {
            reps.push({ ...repData, weight: dist.weight || 1.0 });
          }
        } catch (e) {
          console.warn("Rep lookup failed for district:", dist, e);
        }
      }

      if (reps.length === 0) {
        throw new Error(
          "We found your district but couldn't locate your current representative. " +
          "They may not yet be listed. Please try again later."
        );
      }

      // Step 3: Display rep info and email options
      if (loadingArea) loadingArea.style.display = "none";
      if (resultsArea) resultsArea.style.display = "block";

      if (reps.length > 1) {
        handleMultiDistrict(section, billId, reps);
      } else {
        displayRepInfo(section, reps[0]);
        await generateEmail(section, billId, reps[0]);
      }

    } catch (err) {
      if (loadingArea) loadingArea.style.display = "none";
      showSectionError(section, err.message || "An error occurred. Please try again.");
    } finally {
      if (findBtn) { findBtn.disabled = false; findBtn.textContent = "Find My Rep"; }
    }
  }

  // --- Multi-District Handling ---

  function handleMultiDistrict(section, billId, reps) {
    const resultsArea = $(".tell-rep-results", section);
    if (!resultsArea) return;

    // Sort by weight descending
    reps.sort((a, b) => (b.weight || 0) - (a.weight || 0));
    const primary = reps[0];
    const others = reps.slice(1);

    let html = `
      <div class="multi-district-notice">
        <strong>📍 Your ZIP code covers multiple congressional districts.</strong>
        Showing all representatives — the primary one (most likely yours) is listed first.
      </div>
      <div class="rep-cards-container">
        <div class="rep-card-label">Primary Representative (To:)</div>
        ${buildRepCardHtml(primary)}
    `;

    if (others.length > 0) {
      html += `<div class="rep-card-label">Other Districts in Your ZIP (CC:)</div>`;
      others.forEach((r) => { html += buildRepCardHtml(r); });
    }

    html += `</div>`;
    resultsArea.innerHTML = html;

    // Attach photo error handlers
    attachPhotoFallbacks(resultsArea);

    // Generate email for primary rep
    generateEmail(section, billId, primary, others);
  }

  // --- Display Single Rep ---

  function displayRepInfo(section, rep) {
    const resultsArea = $(".tell-rep-results", section);
    if (!resultsArea) return;

    resultsArea.innerHTML = `
      <div class="rep-cards-container">
        ${buildRepCardHtml(rep)}
      </div>
    `;

    attachPhotoFallbacks(resultsArea);
  }

  function buildRepCardHtml(rep) {
    const name = _escHtml(rep.name || "Unknown");
    const state = _escHtml(rep.state || "");
    const district = rep.district != null ? rep.district : "?";
    const districtLabel = district === 0 ? "At-Large" : `District ${district}`;
    const photoUrl = rep.photo_url || "";
    const initial = name.charAt(0).toUpperCase();

    const photoHtml = photoUrl
      ? `<img src="${_escHtml(photoUrl)}" alt="Photo of ${name}" class="rep-photo" loading="lazy">`
      : `<div class="rep-photo-placeholder">${initial}</div>`;

    return `
      <div class="rep-card" data-bioguide="${_escHtml(rep.bioguideId || "")}">
        ${photoHtml}
        <div class="rep-info">
          <div class="rep-name">${name}</div>
          <div class="rep-district">${state} — ${districtLabel}</div>
          <span class="rep-role-badge">U.S. House</span>
        </div>
      </div>
    `;
  }

  function attachPhotoFallbacks(container) {
    const photos = $all(".rep-photo", container);
    photos.forEach((img) => {
      img.addEventListener("error", () => {
        const initial = (img.alt || "?").replace("Photo of ", "").charAt(0).toUpperCase();
        const placeholder = document.createElement("div");
        placeholder.className = "rep-photo-placeholder";
        placeholder.textContent = initial;
        img.replaceWith(placeholder);
      }, { once: true });
    });
  }

  // --- Email Generation ---

  async function generateEmail(section, billId, primaryRep, ccReps) {
    const resultsArea = $(".tell-rep-results", section);
    if (!resultsArea) return;

    // Capture context so we can regenerate if the vote changes
    repContextByBill.set(billId, {
      section,
      primaryRep,
      ccReps: Array.isArray(ccReps) ? ccReps : [],
    });

    // Get user's vote from localStorage
    const vote = getStored(`voted_${billId}`);
    if (!vote || (vote !== "yes" && vote !== "no")) {
      // Should not happen since we only show this after voting, but handle gracefully
      showEmailEditor(section, {
        subject: `Constituent Feedback | via TeenCivics`,
        body: "Dear Representative,\n\nI am writing as your constituent...\n\nRespectfully,\n\n[Your Name]",
        mailto_url: null,
      }, primaryRep, ccReps);
      return;
    }

    try {
      const resp = await fetch("/api/generate-email", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": randReqId(),
        },
        body: JSON.stringify({
          bill_id: billId,
          vote: vote,
          rep_name: primaryRep.name,
          rep_email: primaryRep.email || null,
        }),
      });

      const emailData = await resp.json();
      if (!resp.ok || emailData.error) {
        throw new Error(emailData.error || "Failed to generate email.");
      }

      showEmailEditor(section, emailData, primaryRep, ccReps);

    } catch (err) {
      console.error("Email generation error:", err);
      // Show a fallback minimal editor
      showEmailEditor(section, {
        subject: `Constituent Feedback on ${billId} | via TeenCivics`,
        body: `Dear Representative ${primaryRep.name ? primaryRep.name.split(" ").pop() : ""},\n\nAs your constituent, I recently reviewed ${billId} on TeenCivics. I voted ${vote.toUpperCase()} on this bill.\n\nI urge you to consider your constituents' views. Thank you for your service.\n\nRespectfully,\n\n[Your Name]`,
        mailto_url: null,
      }, primaryRep, ccReps);
    }
  }

  // Regenerate email if vote changes while panel is open
  async function onVoteChanged(billId, newVote) {
    const ctx = repContextByBill.get(billId);
    if (!ctx) return;

    const { section, primaryRep, ccReps } = ctx;
    if (!section || !section.classList.contains("expanded")) return;

    // Update stored vote direction immediately
    setStored(`voted_${billId}`, newVote);

    const resultsArea = $(".tell-rep-results", section);
    if (!resultsArea) return;

    // Preserve rep cards, refresh editor content
    const editorSection = $(".email-editor-section", resultsArea);
    if (editorSection) {
      editorSection.remove();
    }

    // Fetch new email content and rebuild editor
    await generateEmail(section, billId, primaryRep, ccReps);

    showToast("Message updated for your new vote.");
  }

  // --- Email Editor UI ---

  function showEmailEditor(section, emailData, primaryRep, ccReps) {
    const resultsArea = $(".tell-rep-results", section);
    if (!resultsArea) return;

    const hasEmail = primaryRep.email;
    const hasWebsite = primaryRep.website;

    let editorHtml = "";

    if (hasEmail) {
      // Direct email path
      editorHtml = buildDirectEmailHtml(emailData, primaryRep, ccReps);
    } else if (hasWebsite) {
      // Contact form fallback
      editorHtml = buildContactFallbackHtml(emailData, primaryRep);
    } else {
      // No email, no website — just show copy
      editorHtml = buildCopyOnlyHtml(emailData, primaryRep);
    }

    // Append editor below the rep card(s)
    const editorContainer = document.createElement("div");
    editorContainer.className = "email-editor-section";
    editorContainer.innerHTML = editorHtml;
    resultsArea.appendChild(editorContainer);

    // Bind action buttons
    bindEmailActions(editorContainer, emailData, primaryRep, ccReps);
  }

  function buildDirectEmailHtml(emailData, primaryRep, ccReps) {
    return `
      <h4>📧 Your Email to Rep. ${_escHtml(primaryRep.name || "")}</h4>
      <label for="email-subject" class="visually-hidden">Email subject</label>
      <input type="text" class="email-subject" id="email-subject" 
             value="${_escAttr(emailData.subject)}" aria-label="Email subject line">
      <label for="email-body" class="visually-hidden">Email body</label>
      <textarea class="email-body-textarea" id="email-body" 
                aria-label="Email body">${_escHtml(emailData.body)}</textarea>
      <div class="email-actions">
        <a href="#" class="btn-send-email" role="button" aria-label="Send email">
          ✉️ Send Email
        </a>
        <button class="btn-copy-email" type="button" aria-label="Copy email to clipboard">
          📋 Copy to Clipboard
        </button>
      </div>
    `;
  }

  function buildContactFallbackHtml(emailData, primaryRep) {
    const name = _escHtml(primaryRep.name || "your representative");
    const rawWebsite = primaryRep.website || "#";
    const hasContactFormUrl = Boolean(primaryRep.contactFormUrl);

    // Use direct contact form URL when available, otherwise append /contact to website
    const fallbackUrl = rawWebsite === "#"
      ? "#"
      : rawWebsite.replace(/\/+$/, "") + "/contact";
    const contactUrl = hasContactFormUrl ? primaryRep.contactFormUrl : fallbackUrl;
    const safeContactUrl = _escHtml(contactUrl);

    const linkText = hasContactFormUrl
      ? `Visit Representative ${name}'s contact form:`
      : `Visit Representative ${name}'s website to contact them:`;

    const buttonText = hasContactFormUrl ? "🌐 Visit Contact Form" : "🌐 Visit Website";

    return `
      <div class="contact-fallback">
        <p>${linkText}</p>
        <a href="${safeContactUrl}" target="_blank" rel="noopener" class="btn-contact-website">
          ${buttonText}
        </a>
        <hr class="contact-divider">
        <p class="contact-fallback-hint">Try this message, or write your own!</p>
        <div class="email-readonly-box">${_escHtml(emailData.body)}</div>
        <div class="email-actions" style="justify-content: center;">
          <button class="btn-copy-email" type="button" aria-label="Copy message to clipboard">
            📋 Copy to Clipboard
          </button>
        </div>
      </div>
    `;
  }

  function buildCopyOnlyHtml(emailData, primaryRep) {
    return `
      <div class="contact-fallback">
        <p>We couldn't find a direct contact method for <strong>Representative ${_escHtml(primaryRep.name || "")}</strong>. Here's your message — you can search for their contact form online.</p>
        <div class="email-readonly-box">${_escHtml(emailData.body)}</div>
        <div class="email-actions" style="justify-content: center;">
          <button class="btn-copy-email" type="button" aria-label="Copy message to clipboard">
            📋 Copy to Clipboard
          </button>
        </div>
      </div>
    `;
  }

  // --- Bind Email Action Buttons ---

  function bindEmailActions(container, emailData, primaryRep, ccReps) {
    // Send Email button (mailto)
    const sendBtn = $(".btn-send-email", container);
    if (sendBtn) {
      sendBtn.addEventListener("click", (e) => {
        e.preventDefault();
        // Re-read from the editable fields
        const subjectInput = $(".email-subject", container);
        const bodyTextarea = $(".email-body-textarea", container);
        const subject = subjectInput ? subjectInput.value : emailData.subject;
        const body = bodyTextarea ? bodyTextarea.value : emailData.body;

        const params = new URLSearchParams({ subject, body });
        const email = primaryRep.email || "";
        let mailtoUrl = `mailto:${encodeURIComponent(email)}?${params.toString()}`;

        window.location.href = mailtoUrl;
      });
    }

    // Copy button
    const copyBtns = $all(".btn-copy-email", container);
    copyBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        // Get text from editable textarea or readonly box
        const textarea = $(".email-body-textarea", container);
        const readonlyBox = $(".email-readonly-box", container);
        const subjectInput = $(".email-subject", container);

        let textToCopy = "";
        if (subjectInput) {
          textToCopy += `Subject: ${subjectInput.value}\n\n`;
        }
        if (textarea) {
          textToCopy += textarea.value;
        } else if (readonlyBox) {
          textToCopy += readonlyBox.textContent;
        } else {
          textToCopy += emailData.body;
        }

        copyToClipboard(textToCopy, btn);
      });
    });
  }

  // --- Clipboard ---

  async function copyToClipboard(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
      onCopySuccess(btn);
    } catch (err) {
      // Fallback for older browsers
      try {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.cssText = "position:fixed;opacity:0;pointer-events:none";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
        onCopySuccess(btn);
      } catch (e2) {
        console.error("Copy failed:", e2);
        showToast("Failed to copy — please select and copy manually.");
      }
    }
  }

  function onCopySuccess(btn) {
    showToast("Copied to clipboard!");
  }

  // --- Section Error Handling ---

  function showSectionError(section, message) {
    let errorEl = $(".tell-rep-error", section);
    if (!errorEl) {
      errorEl = document.createElement("div");
      errorEl.className = "tell-rep-error";
      const resultsArea = $(".tell-rep-results", section);
      if (resultsArea) {
        section.insertBefore(errorEl, resultsArea);
      } else {
        section.appendChild(errorEl);
      }
    }
    errorEl.textContent = message;
    errorEl.style.display = "block";
  }

  function hideSectionError(section) {
    const errorEl = $(".tell-rep-error", section);
    if (errorEl) {
      errorEl.style.display = "none";
      errorEl.textContent = "";
    }
  }

  // --- Attribute escaping ---
  function _escAttr(str) {
    return (str || "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  // --- Bootstrap ---

  function bootstrap() {
    initTellRepToggles();
    initZipValidation();
    initFindRepButtons();
    checkExistingVoteForTellRep();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap, { once: true });
  } else {
    bootstrap();
  }

  // --- Public API (for script.js integration) ---
  window.TeenCivics = Object.assign(window.TeenCivics || {}, {
    showTellRepButton,
    onVoteChanged,
  });

})();
