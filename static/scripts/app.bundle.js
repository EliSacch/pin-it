(() => {
  // static/scripts/ui-common.js
  var $ = window.jQuery;
  var prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function setButtonLoading($btn, isLoading) {
    if (!$btn.length) {
      return;
    }
    const $label = $btn.find(".btn-label");
    const $loading = $btn.find(".btn-loading");
    if (isLoading) {
      const loadingText = $btn.data("loading-text") || "Loading...";
      $btn.find(".btn-loading-text").text(loadingText);
      $label.attr("hidden", true);
      $loading.removeAttr("hidden");
      $btn.prop("disabled", true).attr("aria-busy", "true").addClass("is-loading");
      return;
    }
    $label.removeAttr("hidden");
    $loading.attr("hidden", true);
    $btn.prop("disabled", false).removeAttr("aria-busy").removeClass("is-loading");
  }
  function formSubmitButtons($form) {
    return $form.find("button.base-button").filter(function() {
      const type = (this.getAttribute("type") || "submit").toLowerCase();
      return type === "submit";
    });
  }
  function clearFormErrors($form) {
    $form.find(".form-errors").prop("hidden", true).empty();
    $form.find(".form-control").removeClass("is-invalid");
    $form.find("input, select, textarea").each(function() {
      const $field = $(this);
      const baseDescribedBy = $field.attr("data-describedby");
      $field.removeAttr("aria-invalid");
      if (baseDescribedBy) {
        $field.attr("aria-describedby", baseDescribedBy);
      } else {
        $field.removeAttr("aria-describedby");
      }
    });
    $form.find(".form-control-wrapper > .error-msg").prop("hidden", true).empty();
  }
  function renderErrorList(messages) {
    const items = (Array.isArray(messages) ? messages : [messages]).filter(Boolean).map((message) => $("<li></li>").text(message)[0].outerHTML).join("");
    return items ? `<ul>${items}</ul>` : "";
  }
  function showFormErrors($form, errors) {
    clearFormErrors($form);
    if (!errors || typeof errors !== "object") {
      return;
    }
    Object.entries(errors).forEach(([field, messages]) => {
      const html = renderErrorList(messages);
      if (!html) {
        return;
      }
      if (field === "form") {
        $form.find(".form-errors").html(html).prop("hidden", false);
        return;
      }
      const $input = $form.find(`[data-list-name="${field}"], [name="${field}"]`).first();
      if (!$input.length) {
        $form.find(".form-errors").html(html).prop("hidden", false);
        return;
      }
      const $wrapper = $input.closest(".form-control-wrapper");
      let $error = $wrapper.children(".error-msg").first();
      const errorId = $error.attr("id") || `${$input.attr("id") || field}-errors`;
      const describedBy = [$input.attr("data-describedby"), errorId].filter(Boolean).join(" ");
      $input.attr("aria-invalid", "true").attr("aria-describedby", describedBy).closest(".form-control").addClass("is-invalid");
      if (!$error.length) {
        $error = $('<div class="error-msg" role="alert"></div>').attr("id", errorId);
        $wrapper.append($error);
      } else if (!$error.attr("id")) {
        $error.attr("id", errorId);
      }
      $error.html(html).prop("hidden", false);
    });
  }
  function focusFormErrors($form) {
    if (!$form || !$form.length) {
      return;
    }
    const $invalid = $form.find('[aria-invalid="true"]').first();
    if ($invalid.length) {
      $invalid.trigger("focus");
      return;
    }
    const $alert = $form.find('.error-msg[role="alert"]:not([hidden]), .form-errors[role="alert"]:not([hidden])').first();
    if ($alert.length) {
      if (!$alert.attr("tabindex")) {
        $alert.attr("tabindex", "-1");
      }
      $alert.trigger("focus");
    }
  }
  $(function() {
    $(document).on("click", ".skip-link", function(event) {
      const targetId = (this.hash || "").replace(/^#/, "");
      const target = targetId && document.getElementById(targetId);
      if (!target) {
        return;
      }
      event.preventDefault();
      if (!target.hasAttribute("tabindex")) {
        target.setAttribute("tabindex", "-1");
      }
      target.focus({ preventScroll: false });
      if (typeof target.scrollIntoView === "function") {
        target.scrollIntoView();
      }
    });
    $(document).on("click", "#messages .close-button", function() {
      $(this).closest(".message").remove();
    });
    $(document).on("submit", "form", function(event) {
      const $form = $(this);
      const submitter = event.originalEvent && event.originalEvent.submitter;
      let $btn = submitter ? $(submitter) : $();
      if (!$btn.is("button.base-button")) {
        $btn = formSubmitButtons($form);
      }
      if (!$btn.length) {
        return;
      }
      if ($btn.filter(":disabled").length === $btn.length) {
        return false;
      }
      setButtonLoading($btn, true);
    });
  });

  // static/scripts/page-transitions.js
  var $2 = window.jQuery;
  var PAGE_EXIT_MS = 280;
  var PAGE_TRANSITION_KEY = "pinit-page-transition";
  function markPageTransitionTargets() {
    $2("main, .form-wrapper, .error-page").addClass("page-transition-target");
  }
  function clearPendingTransitionFlag() {
    try {
      sessionStorage.removeItem(PAGE_TRANSITION_KEY);
    } catch (err) {
    }
    document.documentElement.classList.remove("is-page-pending");
  }
  function playPageEnter() {
    const shouldEnter = document.documentElement.classList.contains("is-page-pending");
    clearPendingTransitionFlag();
    markPageTransitionTargets();
    if (!shouldEnter || prefersReducedMotion) {
      $2("body").removeClass("is-page-entering is-page-exiting");
      return;
    }
    $2("body").removeClass("is-page-exiting").addClass("is-page-entering");
    window.setTimeout(() => {
      $2("body").removeClass("is-page-entering");
    }, 500);
  }
  function navigateWithTransition(url) {
    if (!url || prefersReducedMotion || $2("body").hasClass("is-page-exiting")) {
      window.location.href = url;
      return;
    }
    try {
      sessionStorage.setItem(PAGE_TRANSITION_KEY, "1");
    } catch (err) {
    }
    const $dashboardsList = $2("#dashboards-list");
    if ($dashboardsList.is(":visible")) {
      $2("#dashboards-toggler").attr("aria-expanded", "false").attr("aria-label", "Open dashboards");
      $dashboardsList.hide().removeClass("dashboards-opening dashboards-closing");
    }
    markPageTransitionTargets();
    $2("body").removeClass("is-page-entering").addClass("is-page-exiting");
    let navigated = false;
    const go = () => {
      if (navigated) {
        return;
      }
      navigated = true;
      window.location.href = url;
    };
    $2(".page-transition-target").first().one("animationend", go);
    window.setTimeout(go, PAGE_EXIT_MS + 80);
  }
  function shouldInterceptNavigation(event, anchor) {
    if (event.defaultPrevented) {
      return false;
    }
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return false;
    }
    if (anchor.target && anchor.target !== "_self") {
      return false;
    }
    if (anchor.hasAttribute("download")) {
      return false;
    }
    let url;
    try {
      url = new URL(anchor.href, window.location.href);
    } catch (err) {
      return false;
    }
    if (url.origin !== window.location.origin) {
      return false;
    }
    if (url.pathname === window.location.pathname && url.search === window.location.search) {
      return false;
    }
    if (url.pathname === window.location.pathname && url.hash) {
      return false;
    }
    return true;
  }
  $2(function() {
    playPageEnter();
    $2(window).on("pageshow", function(event) {
      if (event.originalEvent && event.originalEvent.persisted) {
        clearPendingTransitionFlag();
        $2("body").removeClass("is-page-entering is-page-exiting");
        markPageTransitionTargets();
      }
    });
    $2(document).on("click", "a[href]", function(event) {
      const anchor = this;
      if (!shouldInterceptNavigation(event, anchor)) {
        return;
      }
      event.preventDefault();
      navigateWithTransition(anchor.href);
    });
  });

  // static/scripts/disclosures.js
  var $3 = window.jQuery;
  function closeOptionsMenu(returnFocus) {
    const $toggler = $3("#options-toggler");
    const $options = $3("#options");
    if ($toggler.attr("aria-expanded") !== "true") {
      return;
    }
    $toggler.attr("aria-expanded", "false");
    $toggler.attr("aria-label", "Open options");
    $options.removeClass("options-opening");
    if (prefersReducedMotion) {
      $options.hide().removeClass("options-closing");
    } else {
      $options.addClass("options-closing").one("animationend", () => {
        $options.hide().removeClass("options-closing");
      });
    }
    if (returnFocus) {
      $toggler.trigger("focus");
    }
  }
  function openOptionsMenu() {
    const $toggler = $3("#options-toggler");
    const $options = $3("#options");
    $toggler.attr("aria-expanded", "true");
    $toggler.attr("aria-label", "Close options");
    $options.show().removeClass("options-closing").addClass("options-opening");
    const $firstAction = $options.find("button").first();
    if ($firstAction.length) {
      $firstAction.trigger("focus");
    }
  }
  function closeDashboardsMenu(returnFocus) {
    const $toggler = $3("#dashboards-toggler");
    const $list = $3("#dashboards-list");
    if ($toggler.attr("aria-expanded") !== "true") {
      return;
    }
    $toggler.attr("aria-expanded", "false");
    $toggler.attr("aria-label", "Open dashboards");
    $list.removeClass("dashboards-opening");
    if (prefersReducedMotion) {
      $list.hide().removeClass("dashboards-closing");
    } else {
      $list.addClass("dashboards-closing").one("animationend", () => {
        $list.hide().removeClass("dashboards-closing");
      });
    }
    if (returnFocus) {
      $toggler.trigger("focus");
    }
  }
  function openDashboardsMenu() {
    const $toggler = $3("#dashboards-toggler");
    const $list = $3("#dashboards-list");
    $toggler.attr("aria-expanded", "true");
    $toggler.attr("aria-label", "Close dashboards");
    $list.show().removeClass("dashboards-closing").addClass("dashboards-opening");
    const $firstLink = $list.find("a").first();
    if ($firstLink.length) {
      $firstLink.trigger("focus");
    }
  }
  function closeDisclosureOnFocusLeave($nav, closeFn) {
    $nav.on("focusout", function(event) {
      const next = event.relatedTarget;
      if (next && this.contains(next)) {
        return;
      }
      closeFn(false);
    });
  }
  $3(function() {
    $3("#options-toggler").click(() => {
      const isOpen = $3("#options-toggler").attr("aria-expanded") === "true";
      if (isOpen) {
        closeOptionsMenu(false);
      } else {
        closeDashboardsMenu(false);
        openOptionsMenu();
      }
    });
    $3("#dashboards-toggler").click(() => {
      const isOpen = $3("#dashboards-toggler").attr("aria-expanded") === "true";
      if (isOpen) {
        closeDashboardsMenu(false);
      } else {
        closeOptionsMenu(false);
        openDashboardsMenu();
      }
    });
    $3(document).on("click", function(event) {
      const $target = $3(event.target);
      if (!$target.closest("#options-nav").length) {
        closeOptionsMenu(false);
      }
      if (!$target.closest("#dashboards-nav").length) {
        closeDashboardsMenu(false);
      }
    });
    closeDisclosureOnFocusLeave($3("#options-nav"), closeOptionsMenu);
    closeDisclosureOnFocusLeave($3("#dashboards-nav"), closeDashboardsMenu);
    $3(document).on("keydown", function(e) {
      if (e.key !== "Escape") {
        return;
      }
      if ($3(".overlay.visible").length) {
        return;
      }
      if ($3("#options-toggler").attr("aria-expanded") === "true") {
        closeOptionsMenu(true);
        return;
      }
      if ($3("#dashboards-toggler").attr("aria-expanded") === "true") {
        closeDashboardsMenu(true);
      }
    });
  });

  // static/scripts/list-input.js
  var $4 = window.jQuery;
  var SEPARATOR = /[\s,]+/;
  var emailProbe = document.createElement("input");
  emailProbe.type = "email";
  var itemTypes = {
    text: {
      normalize: (value) => value,
      isValid: () => true,
      invalidMessage: "Remove invalid entries."
    },
    email: {
      normalize: (value) => value.toLowerCase(),
      isValid: (value) => {
        emailProbe.value = value;
        return emailProbe.checkValidity();
      },
      invalidMessage: "Remove or fix invalid email addresses."
    }
  };
  function itemTypeFor($root) {
    return itemTypes[$root.data("item-type")] || itemTypes.text;
  }
  function splitTokens(text) {
    return (text || "").split(SEPARATOR).map((token) => token.trim()).filter(Boolean);
  }
  function entryFor($root) {
    return $root.find(".list-input-entry").first();
  }
  function chipValue($chip) {
    return $chip.find('input[type="hidden"]').val();
  }
  function currentValues($root) {
    return $root.find(".list-input-chip").map(function() {
      return chipValue($4(this));
    }).get();
  }
  function announce($root, message) {
    $root.find(".list-input-status").text(message);
  }
  function markChipValidity($root, $chip) {
    const isValid = itemTypeFor($root).isValid(chipValue($chip));
    $chip.toggleClass("is-invalid", !isValid);
    $chip.find(".list-input-chip-invalid").remove();
    if (!isValid) {
      $chip.find(".list-input-chip-label").append('<span class="visually-hidden list-input-chip-invalid"> (invalid)</span>');
    }
  }
  function syncState($root) {
    const $chips = $root.find(".list-input-chip");
    $root.find(".list-input-chips").prop("hidden", !$chips.length);
    const $entry = entryFor($root);
    const itemLabel = $root.data("item-label") || "item";
    let message = "";
    if ($chips.filter(".is-invalid").length) {
      message = itemTypeFor($root).invalidMessage;
    } else if ($entry.attr("aria-required") === "true" && !$chips.length) {
      message = `Add at least one ${itemLabel}.`;
    }
    $entry.get(0).setCustomValidity(message);
  }
  function buildChip($root, value) {
    const template = $root.find(".list-input-chip-template").get(0);
    const $chip = $4(template.content.firstElementChild.cloneNode(true));
    const itemLabel = $root.data("item-label") || "item";
    $chip.find(".list-input-chip-label").text(value);
    $chip.find(".list-input-chip-remove").attr("aria-label", `Remove ${itemLabel} ${value}`);
    $chip.find('input[type="hidden"]').val(value);
    markChipValidity($root, $chip);
    return $chip;
  }
  function addItems($root, text) {
    const type = itemTypeFor($root);
    const existing = new Set(currentValues($root).map(type.normalize));
    const added = [];
    splitTokens(text).forEach((token) => {
      const value = type.normalize(token);
      if (existing.has(value)) {
        return;
      }
      existing.add(value);
      $root.find(".list-input-chips").append(buildChip($root, value));
      added.push(value);
    });
    syncState($root);
    if (added.length) {
      announce($root, `Added ${added.join(", ")}.`);
    }
  }
  function removeChip($chip, { focusNext = true } = {}) {
    const $root = $chip.closest("[data-list-input]");
    const value = chipValue($chip);
    const $sibling = $chip.next(".list-input-chip").length ? $chip.next(".list-input-chip") : $chip.prev(".list-input-chip");
    $chip.remove();
    syncState($root);
    announce($root, `Removed ${value}.`);
    if (focusNext) {
      const $target = $sibling.length ? $sibling.find(".list-input-chip-remove") : entryFor($root);
      $target.trigger("focus");
    }
  }
  function commitEntry($root) {
    const $entry = entryFor($root);
    const text = $entry.val();
    if (!text || !text.trim()) {
      $entry.val("");
      return;
    }
    $entry.val("");
    addItems($root, text);
  }
  function setItems($root, values) {
    $root.find(".list-input-chip").remove();
    const $chips = $root.find(".list-input-chips");
    values.forEach((value) => $chips.append(buildChip($root, value)));
    syncState($root);
  }
  function commitListInputs($form) {
    $form.find("[data-list-input]").each(function() {
      commitEntry($4(this));
    });
  }
  function initListInput($root) {
    if ($root.data("list-input-ready")) {
      return;
    }
    $root.data("list-input-ready", true);
    $root.data("initial-values", currentValues($root));
    $root.find(".list-input-chip").each(function() {
      markChipValidity($root, $4(this));
    });
    syncState($root);
  }
  $4(function() {
    $4("[data-list-input]").each(function() {
      initListInput($4(this));
    });
    $4(document).on("input", ".list-input-entry", function() {
      const $entry = $4(this);
      const value = $entry.val();
      if (!SEPARATOR.test(value)) {
        return;
      }
      const $root = $entry.closest("[data-list-input]");
      const endsWithSeparator = /[\s,]$/.test(value);
      const tokens = splitTokens(value);
      const pending = endsWithSeparator ? "" : tokens.pop() || "";
      $entry.val(pending);
      addItems($root, tokens.join(","));
    });
    $4(document).on("keydown", ".list-input-entry", function(event) {
      const $entry = $4(this);
      const $root = $entry.closest("[data-list-input]");
      if (event.key === "Enter" && $entry.val().trim()) {
        event.preventDefault();
        commitEntry($root);
        return;
      }
      if (event.key === "Backspace" && !$entry.val()) {
        const $last = $root.find(".list-input-chip").last();
        if ($last.length) {
          event.preventDefault();
          removeChip($last, { focusNext: false });
        }
      }
    });
    $4(document).on("focusout", ".list-input-entry", function() {
      commitEntry($4(this).closest("[data-list-input]"));
    });
    $4(document).on("click", ".list-input-chip-remove", function() {
      removeChip($4(this).closest(".list-input-chip"));
    });
    $4(document).on("reset", "form", function() {
      $4(this).find("[data-list-input]").each(function() {
        const $root = $4(this);
        setItems($root, $root.data("initial-values") || []);
        announce($root, "");
      });
    });
  });

  // static/scripts/modals.js
  var $5 = window.jQuery;
  var $lastModalTrigger = null;
  function setBackgroundInert(isInert) {
    $5("body").children().not(".overlay").each(function() {
      if (isInert) {
        $5(this).attr("inert", "");
      } else {
        $5(this).removeAttr("inert");
      }
    });
  }
  function setModalTerminalState($modal, isTerminal) {
    const $confirm = $modal.find(".modal-confirm");
    const $cancelLabel = $modal.find(".modal-footer .modal-close .btn-label");
    if (isTerminal) {
      $modal.addClass("is-terminal").attr("role", "alertdialog");
      $confirm.prop("disabled", true);
      $cancelLabel.text("Close");
      return;
    }
    $modal.removeClass("is-terminal").attr("role", "dialog");
    $confirm.prop("disabled", false);
    $cancelLabel.text("Cancel");
  }
  function getModalFocusTarget($modal) {
    const $field = $modal.find('.modal-body input:not([type="hidden"]), .modal-body select, .modal-body textarea').filter(":visible").first();
    if ($field.length) {
      return $field;
    }
    const $cancel = $modal.find(".modal-footer .modal-close").filter(":visible").first();
    if ($cancel.length) {
      return $cancel;
    }
    return $modal.find('.modal-close, button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])').filter(":visible").first();
  }
  function openModal($modal, $trigger) {
    $lastModalTrigger = $trigger || null;
    setModalTerminalState($modal, false);
    if (!$modal.parent().is("body")) {
      $modal.appendTo(document.body);
    }
    const formAction = $trigger && $trigger.attr("data-form-action");
    if (formAction) {
      $modal.find("form").first().attr("action", formAction);
    }
    setBackgroundInert(true);
    $modal.removeAttr("inert").attr("aria-hidden", "false").addClass("visible");
    const $focusTarget = getModalFocusTarget($modal);
    if ($focusTarget.length) {
      $focusTarget.trigger("focus");
    }
  }
  function closeModal($modal) {
    setBackgroundInert(false);
    const $returnFocus = $lastModalTrigger && $lastModalTrigger.length ? $lastModalTrigger : $5(".modal-trigger").filter('[data-modal="' + $modal.attr("id") + '"]').first();
    if ($returnFocus.length) {
      $returnFocus.trigger("focus");
    } else if (document.activeElement && $modal[0].contains(document.activeElement)) {
      document.activeElement.blur();
    }
    $modal.removeClass("visible").attr("aria-hidden", "true").attr("inert", "");
    const $form = $modal.find("form").first();
    if ($form.length) {
      clearFormErrors($form);
      $form.trigger("reset");
    }
    setModalTerminalState($modal, false);
    $lastModalTrigger = null;
  }
  async function submitModalForm($modal, $confirmBtn) {
    const $form = $modal.find("form").first();
    if (!$form.length || $modal.hasClass("is-terminal")) {
      return;
    }
    const form = $form.get(0);
    commitListInputs($form);
    if (typeof form.reportValidity === "function" && !form.reportValidity()) {
      return;
    }
    clearFormErrors($form);
    setButtonLoading($confirmBtn, true);
    try {
      const response = await fetch($form.attr("action"), {
        method: ($form.attr("method") || "POST").toUpperCase(),
        body: new FormData(form),
        headers: {
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest"
        },
        credentials: "same-origin"
      });
      let data = null;
      try {
        data = await response.json();
      } catch (err) {
        data = null;
      }
      if (!response.ok || !data || data.ok === false) {
        showFormErrors($form, data && data.errors || {
          form: ["Something went wrong. Please try again."]
        });
        setButtonLoading($confirmBtn, false);
        if (data && data.retryable === false) {
          setModalTerminalState($modal, true);
        }
        focusFormErrors($form);
        return;
      }
      closeModal($modal);
      if (data.redirect_url) {
        navigateWithTransition(data.redirect_url);
      }
    } catch (err) {
      showFormErrors($form, {
        form: ["Something went wrong. Please try again."]
      });
      focusFormErrors($form);
      setButtonLoading($confirmBtn, false);
    }
  }
  $5(function() {
    $5(document).on("click", ".modal-trigger", function() {
      const $trigger = $5(this);
      const $modal = $5(`#${$trigger.attr("data-modal")}`);
      if ($modal.length) {
        openModal($modal, $trigger);
      }
    });
    const $modalWithErrors = $5(".overlay").filter(function() {
      return $5(this).find('.error-msg[role="alert"]:not([hidden]), .form-errors[role="alert"]:not([hidden])').length;
    }).first();
    if ($modalWithErrors.length) {
      openModal($modalWithErrors);
      focusFormErrors($modalWithErrors.find("form").first());
    } else {
      const $formWithErrors = $5("main form").filter(function() {
        return $5(this).find(
          '[aria-invalid="true"], .error-msg[role="alert"]:not([hidden]), .form-errors[role="alert"]:not([hidden])'
        ).length;
      }).first();
      if ($formWithErrors.length) {
        focusFormErrors($formWithErrors);
      }
    }
    $5(document).on("click", ".modal-close", function() {
      const $overlay = $5(this).closest(".overlay");
      if ($overlay.length) {
        closeModal($overlay);
      }
    });
    $5(document).on("click", ".modal-confirm", function() {
      const $confirmBtn = $5(this);
      if ($confirmBtn.prop("disabled")) {
        return;
      }
      const $modal = $confirmBtn.closest(".overlay");
      const action = $modal.data("confirm");
      if (action === "submit-form") {
        submitModalForm($modal, $confirmBtn);
      } else if (action === "logout") {
        setButtonLoading($confirmBtn, true);
        window.location.href = "/logout";
      }
    });
    $5(document).on("submit", '.overlay[data-confirm="submit-form"] form', function(e) {
      e.preventDefault();
      const $modal = $5(this).closest(".overlay");
      submitModalForm($modal, $modal.find(".modal-confirm").first());
    });
    $5(document).on("keydown", function(e) {
      if (e.key !== "Escape") {
        return;
      }
      const $openModal = $5(".overlay.visible").last();
      if ($openModal.length) {
        closeModal($openModal);
      }
    });
  });

  // static/scripts/note-editor.js
  var $6 = window.jQuery;
  var editorsByHolderId = /* @__PURE__ */ new Map();
  function getListTool() {
    return window.EditorjsList || window.List;
  }
  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function storageBlocksToEditorBlocks(storageBlocks) {
    const editorBlocks = [];
    let todoBuffer = [];
    function flushTodos() {
      if (!todoBuffer.length) {
        return;
      }
      editorBlocks.push({
        type: "list",
        data: {
          style: "checklist",
          items: todoBuffer.map((todo) => ({
            content: escapeHtml(todo.text),
            meta: { checked: Boolean(todo.isChecked) },
            items: []
          }))
        }
      });
      todoBuffer = [];
    }
    (storageBlocks || []).forEach((block) => {
      if (!block || typeof block !== "object") {
        return;
      }
      if (block.type === "todo") {
        todoBuffer.push(block);
        return;
      }
      flushTodos();
      if (block.type === "paragraph") {
        editorBlocks.push({
          type: "paragraph",
          data: { text: escapeHtml(block.text) }
        });
      }
    });
    flushTodos();
    return editorBlocks;
  }
  function parseJson(value, fallback) {
    if (value == null || value === "") {
      return fallback;
    }
    if (typeof value === "object") {
      return value;
    }
    try {
      return JSON.parse(value);
    } catch (err) {
      return fallback;
    }
  }
  function resolveInitialEditorData($form) {
    const $holder = $form.find(".note-editor");
    const hidden = parseJson($form.find(".note-content-json").val(), null);
    const storageBlocks = Array.isArray(hidden) ? hidden : parseJson($holder.attr("data-storage-blocks"), []);
    return { blocks: storageBlocksToEditorBlocks(storageBlocks) };
  }
  function focusChecklistItem(editor, blockIndex, atEnd) {
    if (editor.caret && typeof editor.caret.setToBlock === "function") {
      editor.caret.setToBlock(blockIndex, atEnd ? "end" : "start");
    }
    const block = editor.blocks.getBlockByIndex(blockIndex);
    const editable = block && block.holder && block.holder.querySelector('[contenteditable="true"]');
    if (!editable) {
      return;
    }
    editable.focus();
    const selection = window.getSelection && window.getSelection();
    if (!selection) {
      return;
    }
    const range = document.createRange();
    range.selectNodeContents(editable);
    range.collapse(!atEnd);
    selection.removeAllRanges();
    selection.addRange(range);
  }
  async function replaceParagraphWithChecklistItem(editor, blockIndex, itemText) {
    await editor.blocks.delete(blockIndex);
    await editor.blocks.insert(
      "list",
      {
        style: "checklist",
        items: [
          {
            content: itemText || "",
            meta: { checked: false },
            items: []
          }
        ]
      },
      {},
      blockIndex,
      true
    );
    requestAnimationFrame(function() {
      focusChecklistItem(editor, blockIndex, Boolean(itemText));
    });
  }
  function bindDashShortcut(editor, holder) {
    holder.addEventListener("keydown", function(event) {
      if (event.key !== " " && event.key !== "Enter") {
        return;
      }
      if (event.defaultPrevented) {
        return;
      }
      const blockIndex = editor.blocks.getCurrentBlockIndex();
      const block = editor.blocks.getBlockByIndex(blockIndex);
      if (!block || block.name !== "paragraph") {
        return;
      }
      const editable = block.holder && block.holder.querySelector('[contenteditable="true"]');
      const text = (editable && editable.innerText || "").replace(/\u00a0/g, " ").replace(/\n+$/, "");
      if (event.key === " ") {
        if (text !== "--") {
          return;
        }
        event.preventDefault();
        replaceParagraphWithChecklistItem(editor, blockIndex, "").catch(function() {
        });
        return;
      }
      const match = text.match(/^--\s*(.*)$/);
      if (!match) {
        return;
      }
      event.preventDefault();
      replaceParagraphWithChecklistItem(editor, blockIndex, match[1] || "").catch(function() {
      });
    });
  }
  function bindChecklistAccessibility(holder) {
    function focusEditable(el, atStart) {
      el.focus();
      const selection = window.getSelection && window.getSelection();
      if (!selection) {
        return;
      }
      const range = document.createRange();
      range.selectNodeContents(el);
      range.collapse(Boolean(atStart));
      selection.removeAllRanges();
      selection.addRange(range);
    }
    holder.addEventListener("keydown", function(event) {
      if (event.key !== "Tab") {
        return;
      }
      if (!event.target || !event.target.closest) {
        return;
      }
      const listItem = event.target.closest(".cdx-list__item");
      if (!listItem) {
        return;
      }
      const listRoot = listItem.closest(".cdx-list");
      if (!listRoot) {
        return;
      }
      const focusables = Array.from(
        listRoot.querySelectorAll(
          '.cdx-list__checkbox[tabindex="0"], .cdx-list__item-content[contenteditable="true"]'
        )
      );
      const current = event.target.closest(
        ".cdx-list__checkbox, .cdx-list__item-content"
      );
      const index = focusables.indexOf(current);
      if (index === -1) {
        return;
      }
      const nextIndex = event.shiftKey ? index - 1 : index + 1;
      event.stopPropagation();
      event.stopImmediatePropagation();
      if (nextIndex < 0 || nextIndex >= focusables.length) {
        return;
      }
      event.preventDefault();
      const next = focusables[nextIndex];
      if (next.isContentEditable) {
        focusEditable(next, !event.shiftKey);
      } else {
        next.focus();
      }
    }, true);
    let checklistLabelSeq = 0;
    function ensureContentId(content) {
      if (!content.id) {
        checklistLabelSeq += 1;
        content.id = `${holder.id || "note-editor"}-item-${checklistLabelSeq}`;
      }
      return content.id;
    }
    function itemText(content) {
      return (content && (content.innerText || content.textContent) || "").replace(/\u00a0/g, " ").trim();
    }
    function syncCheckboxName(el) {
      const item = el.closest(".cdx-list__item");
      const content = item && item.querySelector(".cdx-list__item-content");
      if (content && itemText(content)) {
        el.setAttribute("aria-labelledby", ensureContentId(content));
        el.removeAttribute("aria-label");
        return;
      }
      el.removeAttribute("aria-labelledby");
      el.setAttribute("aria-label", "Checklist item");
    }
    function syncCheckboxAria(el) {
      el.setAttribute(
        "aria-checked",
        el.classList.contains("cdx-list__checkbox--checked") ? "true" : "false"
      );
      syncCheckboxName(el);
    }
    function enhanceCheckbox(el) {
      if (el.getAttribute("data-a11y") === "1") {
        syncCheckboxAria(el);
        return;
      }
      el.setAttribute("data-a11y", "1");
      el.setAttribute("role", "checkbox");
      el.setAttribute("tabindex", "0");
      syncCheckboxAria(el);
      el.addEventListener("keydown", function(event) {
        if (event.key !== " " && event.key !== "Enter") {
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        el.click();
        syncCheckboxAria(el);
      });
    }
    function enhanceAll() {
      holder.querySelectorAll(".cdx-list__checkbox").forEach(enhanceCheckbox);
    }
    enhanceAll();
    holder.addEventListener("input", enhanceAll);
    const observer = new MutationObserver(enhanceAll);
    observer.observe(holder, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class"]
    });
  }
  function initNoteEditor($form) {
    if (!$form || !$form.length) {
      return Promise.resolve(null);
    }
    const $holder = $form.find(".note-editor");
    if (!$holder.length) {
      return Promise.resolve(null);
    }
    const holderId = $holder.attr("id");
    if (!holderId) {
      return Promise.resolve(null);
    }
    if (editorsByHolderId.has(holderId)) {
      return Promise.resolve(editorsByHolderId.get(holderId));
    }
    if (typeof window.EditorJS !== "function" || typeof window.Paragraph !== "function") {
      console.error("Editor.js tools are not loaded.");
      return Promise.resolve(null);
    }
    const ListTool = getListTool();
    if (typeof ListTool !== "function") {
      console.error("Editor.js List tool is not loaded.");
      return Promise.resolve(null);
    }
    const holder = $holder.get(0);
    const placeholder = $holder.data("placeholder") || "Type something...";
    const initialData = resolveInitialEditorData($form);
    const editor = new window.EditorJS({
      holder,
      placeholder,
      data: initialData,
      autofocus: false,
      minHeight: 50,
      tools: {
        paragraph: {
          class: window.Paragraph,
          inlineToolbar: false
        },
        list: {
          class: ListTool,
          inlineToolbar: false,
          config: {
            defaultStyle: "checklist",
            maxLevel: 1
          }
        }
      }
    });
    editorsByHolderId.set(holderId, editor);
    return editor.isReady.then(function() {
      bindDashShortcut(editor, holder);
      bindChecklistAccessibility(holder);
      return editor;
    }).catch(function() {
      return editor;
    });
  }
  async function destroyNoteEditor($form) {
    if (!$form || !$form.length) {
      return;
    }
    const $holder = $form.find(".note-editor");
    const holderId = $holder.attr("id");
    if (!holderId || !editorsByHolderId.has(holderId)) {
      return;
    }
    const editor = editorsByHolderId.get(holderId);
    editorsByHolderId.delete(holderId);
    try {
      if (editor && typeof editor.destroy === "function") {
        await editor.destroy();
      }
    } catch (err) {
    }
    $holder.empty();
  }
  async function destroyAllNoteEditors() {
    const forms = $6(".note-form").toArray();
    for (let i = 0; i < forms.length; i += 1) {
      await destroyNoteEditor($6(forms[i]));
    }
  }
  function getEditorForForm($form) {
    const holderId = $form.find(".note-editor").attr("id");
    return holderId ? editorsByHolderId.get(holderId) : null;
  }
  function clearNoteFormErrors($form) {
    if (!$form || !$form.length) {
      return;
    }
    $form.find(".error-msg").prop("hidden", true).empty().removeAttr("tabindex");
    $form.find(".note-title").removeAttr("aria-invalid aria-describedby");
    setNoteSaveBusy($form, false);
  }
  function setNoteSaveBusy($form, isBusy) {
    const $btn = $form.find(".save-btn");
    if (!$btn.length) {
      return;
    }
    const $label = $btn.find(".btn-label");
    const $loading = $btn.find(".btn-loading");
    const idleLabel = $btn.attr("data-idle-label") || $btn.attr("aria-label") || "Save note";
    const loadingText = $btn.data("loading-text") || "Saving note...";
    if (!$btn.attr("data-idle-label")) {
      $btn.attr("data-idle-label", idleLabel);
    }
    if (isBusy) {
      $btn.find(".btn-loading-text").text(loadingText);
      $label.attr("hidden", true);
      $loading.removeAttr("hidden");
      $btn.prop("disabled", true).attr("aria-busy", "true").attr("aria-label", loadingText).addClass("is-loading");
      return;
    }
    $label.removeAttr("hidden");
    $loading.attr("hidden", true);
    $btn.prop("disabled", false).removeAttr("aria-busy").attr("aria-label", $btn.attr("data-idle-label") || idleLabel).removeClass("is-loading");
  }
  function showNoteTitleErrors($form, messages) {
    const $errorField = $form.find(".error-msg").first();
    const $title = $form.find(".note-title").first();
    if (!$errorField.length) {
      return;
    }
    $errorField.prop("hidden", false).html((messages || []).map(function(msg) {
      return $6("<li>").text(msg)[0].outerHTML;
    }).join(""));
    const errorId = $errorField.attr("id");
    $title.attr("aria-invalid", "true");
    if (errorId) {
      $title.attr("aria-describedby", errorId);
    }
    $title.trigger("focus");
  }
  $6(document).on("submit", ".note-form", function(event) {
    const $form = $6(this);
    const $errorField = $form.find(".error-msg");
    const title = $form.find(".note-title").val();
    const errors = [];
    if (title === "" || title == null) {
      errors.push("A title is required.");
    }
    if (errors.length > 0) {
      event.preventDefault();
      event.stopImmediatePropagation();
      setNoteSaveBusy($form, false);
      showNoteTitleErrors($form, errors);
      return;
    }
    const editor = getEditorForForm($form);
    if (!editor) {
      return;
    }
    event.preventDefault();
    if ($form.find(".save-btn").attr("aria-busy") === "true") {
      return;
    }
    setNoteSaveBusy($form, true);
    editor.save().then(function(output) {
      $form.find(".note-content-json").val(JSON.stringify(output));
      $form.off("submit.noteEditorSubmit");
      HTMLFormElement.prototype.submit.call($form.get(0));
    }).catch(function() {
      setNoteSaveBusy($form, false);
      if ($errorField.length) {
        $errorField.prop("hidden", false).attr("tabindex", "-1").html("<li>Could not save note content. Please try again.</li>");
        $errorField.trigger("focus");
      }
    });
  });
  function announceStatus(message) {
    const region = document.getElementById("a11y-status");
    if (!region) {
      return;
    }
    region.textContent = "";
    window.setTimeout(function() {
      region.textContent = message;
    }, 50);
  }
  $6(document).on("change", ".note-todo-checkbox", function() {
    const $checkbox = $6(this);
    const url = $checkbox.data("toggle-url");
    const csrf = $checkbox.data("csrf");
    if (!url || !csrf) {
      return;
    }
    const wasChecked = !$checkbox.prop("checked");
    $checkbox.prop("disabled", true);
    $6.ajax({
      url,
      method: "POST",
      data: { csrf_token: csrf },
      headers: { "X-Requested-With": "XMLHttpRequest" },
      dataType: "json"
    }).done(function(response) {
      if (!response || !response.ok) {
        $checkbox.prop("checked", wasChecked);
        announceStatus("Could not update checklist item. Please try again.");
        return;
      }
      $checkbox.prop("checked", Boolean(response.isChecked));
      $checkbox.closest(".note-todo").toggleClass("is-checked", Boolean(response.isChecked));
    }).fail(function() {
      $checkbox.prop("checked", wasChecked);
      announceStatus("Could not update checklist item. Please try again.");
    }).always(function() {
      $checkbox.prop("disabled", false);
    });
  });
  $6(function() {
    $6(".note-form").each(function() {
      const $form = $6(this);
      const $wrapper = $form.closest("#addNoteForm, .note-edit");
      if ($wrapper.length && !$wrapper.hasClass("hidden-form")) {
        initNoteEditor($form);
      }
    });
  });
  var NoteEditor = {
    init: initNoteEditor,
    destroy: destroyNoteEditor,
    destroyAll: destroyAllNoteEditors,
    clearErrors: clearNoteFormErrors
  };

  // static/scripts/notes-ui.js
  var $7 = window.jQuery;
  function focusNoteForm($form) {
    if (!$form || !$form.length) {
      return;
    }
    const title = $form.find(".note-title").get(0);
    if (!title) {
      return;
    }
    window.requestAnimationFrame(function() {
      window.requestAnimationFrame(function() {
        title.focus({ preventScroll: true });
        if (typeof title.setSelectionRange === "function") {
          const len = title.value.length;
          title.setSelectionRange(len, len);
        }
      });
    });
  }
  function clearNoteErrors($form) {
    if (NoteEditor && typeof NoteEditor.clearErrors === "function") {
      NoteEditor.clearErrors($form);
      return;
    }
    $form.find(".error-msg").prop("hidden", true).empty();
    $form.find(".note-title").removeAttr("aria-invalid aria-describedby");
  }
  function closeAllNoteEdits() {
    const destroyPromises = [];
    $7(".note-slot").each(function() {
      const $slot = $7(this);
      const $form = $slot.find(".note-form");
      clearNoteErrors($form);
      if (NoteEditor && typeof NoteEditor.destroy === "function") {
        destroyPromises.push(NoteEditor.destroy($form));
      }
      $form.trigger("reset");
      $slot.find(".note-edit").addClass("hidden-form");
      $slot.find(".note-view").removeClass("hidden-form");
    });
    return Promise.all(destroyPromises);
  }
  function closeAddNoteForm() {
    const $addForm = $7("#addNoteForm");
    const $form = $addForm.find(".note-form");
    clearNoteErrors($form);
    let destroyPromise = Promise.resolve();
    if (NoteEditor && typeof NoteEditor.destroy === "function") {
      destroyPromise = NoteEditor.destroy($form);
    }
    $form.trigger("reset");
    $addForm.addClass("hidden-form");
    return destroyPromise;
  }
  $7(function() {
    $7(document).on("click", ".edit-btn", function() {
      const $slot = $7(this).closest(".note-slot");
      if (!$slot.length) {
        return;
      }
      Promise.all([closeAddNoteForm(), closeAllNoteEdits()]).then(function() {
        $slot.find(".note-view").addClass("hidden-form");
        $slot.find(".note-edit").removeClass("hidden-form");
        const $form = $slot.find(".note-form");
        const initPromise = NoteEditor && typeof NoteEditor.init === "function" ? NoteEditor.init($form) : Promise.resolve();
        return Promise.resolve(initPromise).then(function() {
          focusNoteForm($form);
        });
      });
    });
    $7(document).on("click", ".note-form .cancel-btn", function() {
      const $form = $7(this).closest(".note-form");
      const $slot = $7(this).closest(".note-slot");
      clearNoteErrors($form);
      const destroyPromise = NoteEditor && typeof NoteEditor.destroy === "function" ? NoteEditor.destroy($form) : Promise.resolve();
      destroyPromise.then(function() {
        $form.trigger("reset");
        if ($slot.length) {
          $slot.find(".note-edit").addClass("hidden-form");
          $slot.find(".note-view").removeClass("hidden-form");
          $slot.find(".edit-btn").first().trigger("focus");
        } else {
          $7("#addNoteForm").addClass("hidden-form");
          $7("#addNoteButton").trigger("focus");
        }
      });
    });
    $7("#addNoteButton").click(() => {
      closeOptionsMenu(false);
      closeAllNoteEdits().then(function() {
        const $addForm = $7("#addNoteForm");
        $addForm.removeClass("hidden-form");
        const $form = $addForm.find(".note-form");
        const initPromise = NoteEditor && typeof NoteEditor.init === "function" ? NoteEditor.init($form) : Promise.resolve();
        return Promise.resolve(initPromise).then(function() {
          focusNoteForm($form);
        });
      });
    });
  });

  // static/scripts/profile-inline.js
  var $8 = window.jQuery;
  var editButtonSelector = ".profile-inline-edit-btn, [data-inline-editor-trigger]";
  var editPanelSelector = ".profile-inline-edit, [data-inline-editor-panel]";
  var viewSelector = ".profile-inline-view, [data-inline-editor-view]";
  function closeProfileInlineEditor($item) {
    const $form = $item.find("form");
    $form.trigger("reset");
    $form.find(".error-msg").prop("hidden", true).find("ul").empty();
    $form.find("[aria-invalid]").removeAttr("aria-invalid aria-describedby");
    $item.find(editPanelSelector).addClass("hidden-form");
    $item.find(viewSelector).removeClass("hidden-form");
    $item.find(editButtonSelector).attr("aria-expanded", "false").first().trigger("focus");
  }
  $8(function() {
    $8(document).on("click", editButtonSelector, function() {
      const $item = $8(this).closest("[data-inline-editor]");
      $item.find(viewSelector).addClass("hidden-form");
      $item.find(editPanelSelector).removeClass("hidden-form");
      $8(this).attr("aria-expanded", "true");
      $item.find(editPanelSelector).find('input:not([type="hidden"])').first().trigger("focus");
    });
    $8(document).on("click", "[data-inline-editor] .cancel-btn", function() {
      closeProfileInlineEditor($8(this).closest("[data-inline-editor]"));
    });
    $8(document).on("keydown", "[data-inline-editor]", function(event) {
      if (event.key !== "Escape") {
        return;
      }
      const $item = $8(this);
      if (!$item.find(editPanelSelector).hasClass("hidden-form")) {
        closeProfileInlineEditor($item);
      }
    });
    $8("[data-inline-editor]").find(editPanelSelector).filter(":not(.hidden-form)").find('input[aria-invalid="true"]').first().trigger("focus");
  });
})();
