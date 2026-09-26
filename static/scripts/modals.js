/**
 * Modal open / close.
 * Page behind the dialog is inert while open; dialog is inert while closed.
 * Move focus out before hiding so AT users aren't trapped in aria-hidden.
 */
import {
    clearFormErrors,
    focusFormErrors,
    setButtonLoading,
    showFormErrors,
} from './ui-common.js';
import { commitListInputs } from './list-input.js';
import { navigateWithTransition } from './page-transitions.js';

const $ = window.jQuery;
let $lastModalTrigger = null;

function setBackgroundInert(isInert) {
    $('body').children().not('.overlay').each(function () {
        if (isInert) {
            $(this).attr('inert', '');
        } else {
            $(this).removeAttr('inert');
        }
    });
}

function setModalTerminalState($modal, isTerminal) {
    const $confirm = $modal.find('.modal-confirm');
    const $cancelLabel = $modal.find('.modal-footer .modal-close .btn-label');

    if (isTerminal) {
        $modal.addClass('is-terminal').attr('role', 'alertdialog');
        $confirm.prop('disabled', true);
        $cancelLabel.text('Close');
        return;
    }

    $modal.removeClass('is-terminal').attr('role', 'dialog');
    $confirm.prop('disabled', false);
    $cancelLabel.text('Cancel');
}

function getModalFocusTarget($modal) {
    const $field = $modal
        .find('.modal-body input:not([type="hidden"]), .modal-body select, .modal-body textarea')
        .filter(':visible')
        .first();
    if ($field.length) {
        return $field;
    }

    const $cancel = $modal.find('.modal-footer .modal-close').filter(':visible').first();
    if ($cancel.length) {
        return $cancel;
    }

    return $modal
        .find('.modal-close, button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
        .filter(':visible')
        .first();
}

function openModal($modal, $trigger) {
    $lastModalTrigger = $trigger || null;
    setModalTerminalState($modal, false);

    if (!$modal.parent().is('body')) {
        $modal.appendTo(document.body);
    }

    const formAction = $trigger && $trigger.attr('data-form-action');
    if (formAction) {
        $modal.find('form').first().attr('action', formAction);
    }

    setBackgroundInert(true);

    $modal
        .removeAttr('inert')
        .attr('aria-hidden', 'false')
        .addClass('visible');

    const $focusTarget = getModalFocusTarget($modal);
    if ($focusTarget.length) {
        $focusTarget.trigger('focus');
    }
}

function closeModal($modal) {
    // Clear page inert first so the trigger can receive focus again.
    setBackgroundInert(false);

    const $returnFocus = $lastModalTrigger && $lastModalTrigger.length
        ? $lastModalTrigger
        : $('.modal-trigger').filter('[data-modal="' + $modal.attr('id') + '"]').first();

    if ($returnFocus.length) {
        $returnFocus.trigger('focus');
    } else if (document.activeElement && $modal[0].contains(document.activeElement)) {
        document.activeElement.blur();
    }

    $modal
        .removeClass('visible')
        .attr('aria-hidden', 'true')
        .attr('inert', '');

    const $form = $modal.find('form').first();
    if ($form.length) {
        clearFormErrors($form);
        $form.trigger('reset');
    }

    setModalTerminalState($modal, false);
    $lastModalTrigger = null;
}

async function submitModalForm($modal, $confirmBtn) {
    const $form = $modal.find('form').first();
    if (!$form.length || $modal.hasClass('is-terminal')) {
        return;
    }

    const form = $form.get(0);
    commitListInputs($form);
    if (typeof form.reportValidity === 'function' && !form.reportValidity()) {
        return;
    }

    clearFormErrors($form);
    setButtonLoading($confirmBtn, true);

    try {
        const response = await fetch($form.attr('action'), {
            method: ($form.attr('method') || 'POST').toUpperCase(),
            body: new FormData(form),
            headers: {
                Accept: 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
            credentials: 'same-origin',
        });

        let data = null;
        try {
            data = await response.json();
        } catch (err) {
            data = null;
        }

        if (!response.ok || !data || data.ok === false) {
            showFormErrors($form, (data && data.errors) || {
                form: ['Something went wrong. Please try again.'],
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
            form: ['Something went wrong. Please try again.'],
        });
        focusFormErrors($form);
        setButtonLoading($confirmBtn, false);
    }
}

$(function () {
    $(document).on('click', '.modal-trigger', function () {
        const $trigger = $(this);
        const $modal = $(`#${$trigger.attr('data-modal')}`);
        if ($modal.length) {
            openModal($modal, $trigger);
        }
    });

    const $modalWithErrors = $('.overlay').filter(function () {
        return $(this).find('.error-msg[role="alert"]:not([hidden]), .form-errors[role="alert"]:not([hidden])').length;
    }).first();
    if ($modalWithErrors.length) {
        openModal($modalWithErrors);
        focusFormErrors($modalWithErrors.find('form').first());
    } else {
        const $formWithErrors = $('main form').filter(function () {
            return $(this).find(
                '[aria-invalid="true"], .error-msg[role="alert"]:not([hidden]), .form-errors[role="alert"]:not([hidden])'
            ).length;
        }).first();
        if ($formWithErrors.length) {
            focusFormErrors($formWithErrors);
        }
    }

    $(document).on('click', '.modal-close', function () {
        const $overlay = $(this).closest('.overlay');
        if ($overlay.length) {
            closeModal($overlay);
        }
    });

    $(document).on('click', '.modal-confirm', function () {
        const $confirmBtn = $(this);
        if ($confirmBtn.prop('disabled')) {
            return;
        }

        const $modal = $confirmBtn.closest('.overlay');
        const action = $modal.data('confirm');

        if (action === 'submit-form') {
            submitModalForm($modal, $confirmBtn);
        } else if (action === 'logout') {
            setButtonLoading($confirmBtn, true);
            window.location.href = '/logout';
        }
    });

    $(document).on('submit', '.overlay[data-confirm="submit-form"] form', function (e) {
        e.preventDefault();
        const $modal = $(this).closest('.overlay');
        submitModalForm($modal, $modal.find('.modal-confirm').first());
    });

    $(document).on('keydown', function (e) {
        if (e.key !== 'Escape') {
            return;
        }
        const $openModal = $('.overlay.visible').last();
        if ($openModal.length) {
            closeModal($openModal);
        }
    });
});
