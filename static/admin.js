// TeenCivics Admin JavaScript
// IIFE pattern matching existing script.js

const AdminApp = (() => {
  "use strict";

  // --- Toast notifications ---
  function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `admin-toast admin-toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    // Auto-dismiss after 4 seconds
    setTimeout(() => {
      toast.classList.add("removing");
      setTimeout(() => {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 300);
    }, 4000);
  }

  // --- Confirmation modal ---
  let _confirmCallback = null;

  function showConfirmModal(message, onConfirm) {
    const modal = document.getElementById("confirm-modal");
    const msgEl = document.getElementById("confirm-modal-message");
    const yesBtn = document.getElementById("confirm-modal-yes");
    if (!modal || !msgEl || !yesBtn) return;

    msgEl.textContent = message;
    modal.style.display = "flex";
    _confirmCallback = onConfirm;

    // Replace event listener (clone trick to remove old listeners)
    const newYes = yesBtn.cloneNode(true);
    yesBtn.parentNode.replaceChild(newYes, yesBtn);
    newYes.id = "confirm-modal-yes";
    newYes.addEventListener("click", () => {
      hideConfirmModal();
      if (_confirmCallback) _confirmCallback();
    });
  }

  function hideConfirmModal() {
    const modal = document.getElementById("confirm-modal");
    if (modal) modal.style.display = "none";
    _confirmCallback = null;
  }

  // --- Get CSRF token from form ---
  function getCSRFToken() {
    const input = document.querySelector('input[name="csrf_token"]');
    return input ? input.value : "";
  }

  // --- Generic row save (edit_row.html) ---
  function handleSave() {
    showConfirmModal("Are you sure you want to save these changes?", () => {
      doSaveRow();
    });
  }

  function doSaveRow() {
    const form = document.getElementById("edit-row-form");
    if (!form) return;

    const table = form.dataset.table;
    const rowId = form.dataset.rowId;
    const csrfToken = getCSRFToken();

    // Collect form data
    const data = {};
    const inputs = form.querySelectorAll("input[name], textarea[name], select[name]");
    inputs.forEach((input) => {
      if (input.name === "csrf_token") return;
      data[input.name] = input.value;
    });

    fetch(`/admin/api/rows/${table}/${rowId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify(data),
    })
      .then(async (response) => {
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.error || `HTTP ${response.status}`);
        }
        return result;
      })
      .then((result) => {
        showToast("Changes saved successfully!", "success");
      })
      .catch((error) => {
        console.error("Save error:", error);
        showToast(`Error: ${error.message}`, "error");
      });
  }

  // --- Bill summary save (bill_summary.html) ---
  function handleBillSummarySave() {
    showConfirmModal("Are you sure you want to save these summary changes?", () => {
      doSaveBillSummary();
    });
  }

  function doSaveBillSummary() {
    const form = document.getElementById("bill-summary-form");
    if (!form) return;

    const table = form.dataset.table;
    const rowId = form.dataset.rowId;
    const csrfToken = getCSRFToken();

    // Collect form data
    const data = {};
    const inputs = form.querySelectorAll("input[name], textarea[name], select[name]");
    inputs.forEach((input) => {
      if (input.name === "csrf_token") return;
      data[input.name] = input.value;
    });

    fetch(`/admin/api/rows/${table}/${rowId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify(data),
    })
      .then(async (response) => {
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.error || `HTTP ${response.status}`);
        }
        return result;
      })
      .then((result) => {
        showToast("Bill summary saved successfully!", "success");
      })
      .catch((error) => {
        console.error("Save error:", error);
        showToast(`Error: ${error.message}`, "error");
      });
  }

  // --- Keyboard shortcut: Escape closes modal ---
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      hideConfirmModal();
    }
  });

  // --- Public API ---
  return {
    showToast,
    showConfirmModal,
    hideConfirmModal,
    handleSave,
    handleBillSummarySave,
  };
})();
