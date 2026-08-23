/**
 * Shared UI helpers (loading buttons, form errors, skip link).
 */
const $ = window.jQuery;

export const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export function setButtonLoading($btn, isLoading) {
    if (!$btn.length) {
        return;
    }

    const $label = $btn.find('.btn-label');
    const $loading = $btn.find('.btn-loading');

    if (isLoading) {
        const loadingText = $btn.data('loading-text') || 'Loading...';
        $btn.find('.btn-loading-text').text(loadingText);
        $label.attr('hidden', true);
        $loading.removeAttr('hidden');
        $btn
            .prop('disabled', true)
            .attr('aria-busy', 'true')
            .addClass('is-loading');
        return;
    }

    $label.removeAttr('hidden');
    $loading.attr('hidden', true);
    $btn
        .prop('disabled', false)
        .removeAttr('aria-busy')
        .removeClass('is-loading');
}

export function formSubmitButtons($form) {
    return $form.find('button.base-button').filter(function () {
        const type = (this.getAttribute('type') || 'submit').toLowerCase();
        return type === 'submit';
    });
}

export function clearFormErrors($form) {
    $form.find('.form-errors').prop('hidden', true).empty();
    $form.find('.form-control').removeClass('is-invalid');
    $form.find('input, select, textarea').removeAttr('aria-invalid aria-describedby');
    $form.find('.form-control-wrapper > .error-msg').prop('hidden', true).empty();
}

export function renderErrorList(messages) {
    const items = (Array.isArray(messages) ? messages : [messages])
        .filter(Boolean)
        .map((message) => $('<li></li>').text(message)[0].outerHTML)
        .join('');
    return items ? `<ul>${items}</ul>` : '';
}

export function showFormErrors($form, errors) {
    clearFormErrors($form);
    if (!errors || typeof errors !== 'object') {
        return;
    }

    Object.entries(errors).forEach(([field, messages]) => {
        const html = renderErrorList(messages);
        if (!html) {
            return;
        }

        if (field === 'form') {
            $form.find('.form-errors').html(html).prop('hidden', false);
            return;
        }

        const $input = $form.find(`[name="${field}"]`).first();
        if (!$input.length) {
            $form.find('.form-errors').html(html).prop('hidden', false);
            return;
        }

        const $wrapper = $input.closest('.form-control-wrapper');
        let $error = $wrapper.find('.error-msg').first();
        const errorId = $error.attr('id') || `${$input.attr('id') || field}-errors`;
        $input
            .attr('aria-invalid', 'true')
            .attr('aria-describedby', errorId)
            .closest('.form-control')
            .addClass('is-invalid');

        if (!$error.length) {
            $error = $('<div class="error-msg" role="alert"></div>').attr('id', errorId);
            $wrapper.append($error);
        } else if (!$error.attr('id')) {
            $error.attr('id', errorId);
        }
        $error.html(html).prop('hidden', false);
    });
}

export function focusFormErrors($form) {
    if (!$form || !$form.length) {
        return;
    }
    const $invalid = $form.find('[aria-invalid="true"]').first();
    if ($invalid.length) {
        $invalid.trigger('focus');
        return;
    }
    const $alert = $form.find('.error-msg[role="alert"]:not([hidden]), .form-errors[role="alert"]:not([hidden])').first();
    if ($alert.length) {
        if (!$alert.attr('tabindex')) {
            $alert.attr('tabindex', '-1');
        }
        $alert.trigger('focus');
    }
}

$(function () {
    $(document).on('click', '.skip-link', function (event) {
        const targetId = (this.hash || '').replace(/^#/, '');
        const target = targetId && document.getElementById(targetId);
        if (!target) {
            return;
        }
        event.preventDefault();
        if (!target.hasAttribute('tabindex')) {
            target.setAttribute('tabindex', '-1');
        }
        target.focus({ preventScroll: false });
        if (typeof target.scrollIntoView === 'function') {
            target.scrollIntoView();
        }
    });

    $(document).on('submit', 'form', function (event) {
        const $form = $(this);
        const submitter = event.originalEvent && event.originalEvent.submitter;
        let $btn = submitter ? $(submitter) : $();
        if (!$btn.is('button.base-button')) {
            $btn = formSubmitButtons($form);
        }
        if (!$btn.length) {
            return;
        }
        if ($btn.filter(':disabled').length === $btn.length) {
            return false;
        }

        setButtonLoading($btn, true);
    });
});
