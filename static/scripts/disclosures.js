/**
 * Options / dashboards disclosures.
 */
import { prefersReducedMotion } from './ui-common.js';

const $ = window.jQuery;

export function closeOptionsMenu(returnFocus) {
    const $toggler = $('#options-toggler');
    const $options = $('#options');
    if ($toggler.attr('aria-expanded') !== 'true') {
        return;
    }

    $toggler.attr('aria-expanded', 'false');
    $toggler.attr('aria-label', 'Open options');
    $options.removeClass('options-opening');

    if (prefersReducedMotion) {
        $options.hide().removeClass('options-closing');
    } else {
        $options
            .addClass('options-closing')
            .one('animationend', () => {
                $options.hide().removeClass('options-closing');
            });
    }

    if (returnFocus) {
        $toggler.trigger('focus');
    }
}

export function openOptionsMenu() {
    const $toggler = $('#options-toggler');
    const $options = $('#options');

    $toggler.attr('aria-expanded', 'true');
    $toggler.attr('aria-label', 'Close options');
    $options
        .show()
        .removeClass('options-closing')
        .addClass('options-opening');

    const $firstAction = $options.find('button').first();
    if ($firstAction.length) {
        $firstAction.trigger('focus');
    }
}

export function closeDashboardsMenu(returnFocus) {
    const $toggler = $('#dashboards-toggler');
    const $list = $('#dashboards-list');
    if ($toggler.attr('aria-expanded') !== 'true') {
        return;
    }

    $toggler.attr('aria-expanded', 'false');
    $toggler.attr('aria-label', 'Open dashboards');
    $list.removeClass('dashboards-opening');

    if (prefersReducedMotion) {
        $list.hide().removeClass('dashboards-closing');
    } else {
        $list
            .addClass('dashboards-closing')
            .one('animationend', () => {
                $list.hide().removeClass('dashboards-closing');
            });
    }

    if (returnFocus) {
        $toggler.trigger('focus');
    }
}

export function openDashboardsMenu() {
    const $toggler = $('#dashboards-toggler');
    const $list = $('#dashboards-list');

    $toggler.attr('aria-expanded', 'true');
    $toggler.attr('aria-label', 'Close dashboards');
    $list
        .show()
        .removeClass('dashboards-closing')
        .addClass('dashboards-opening');

    const $firstLink = $list.find('a').first();
    if ($firstLink.length) {
        $firstLink.trigger('focus');
    }
}

function closeDisclosureOnFocusLeave($nav, closeFn) {
    $nav.on('focusout', function (event) {
        const next = event.relatedTarget;
        if (next && this.contains(next)) {
            return;
        }
        closeFn(false);
    });
}

$(function () {
    $('#options-toggler').click(() => {
        const isOpen = $('#options-toggler').attr('aria-expanded') === 'true';
        if (isOpen) {
            closeOptionsMenu(false);
        } else {
            closeDashboardsMenu(false);
            openOptionsMenu();
        }
    });

    $('#dashboards-toggler').click(() => {
        const isOpen = $('#dashboards-toggler').attr('aria-expanded') === 'true';
        if (isOpen) {
            closeDashboardsMenu(false);
        } else {
            closeOptionsMenu(false);
            openDashboardsMenu();
        }
    });

    $(document).on('click', function (event) {
        const $target = $(event.target);
        if (!$target.closest('#options-nav').length) {
            closeOptionsMenu(false);
        }
        if (!$target.closest('#dashboards-nav').length) {
            closeDashboardsMenu(false);
        }
    });

    closeDisclosureOnFocusLeave($('#options-nav'), closeOptionsMenu);
    closeDisclosureOnFocusLeave($('#dashboards-nav'), closeDashboardsMenu);

    $(document).on('keydown', function (e) {
        if (e.key !== 'Escape') {
            return;
        }
        if ($('.overlay.visible').length) {
            return;
        }
        if ($('#options-toggler').attr('aria-expanded') === 'true') {
            closeOptionsMenu(true);
            return;
        }
        if ($('#dashboards-toggler').attr('aria-expanded') === 'true') {
            closeDashboardsMenu(true);
        }
    });
});
