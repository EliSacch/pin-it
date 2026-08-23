/**
 * Page transitions (dashboard switches and same-origin navigations).
 */
import { prefersReducedMotion } from './ui-common.js';

const $ = window.jQuery;
const PAGE_EXIT_MS = 280;
const PAGE_TRANSITION_KEY = 'pinit-page-transition';

function markPageTransitionTargets() {
    $('main, .form-wrapper, .error-page').addClass('page-transition-target');
}

function clearPendingTransitionFlag() {
    try {
        sessionStorage.removeItem(PAGE_TRANSITION_KEY);
    } catch (err) {
        /* ignore */
    }
    document.documentElement.classList.remove('is-page-pending');
}

function playPageEnter() {
    const shouldEnter = document.documentElement.classList.contains('is-page-pending');
    clearPendingTransitionFlag();
    markPageTransitionTargets();

    if (!shouldEnter || prefersReducedMotion) {
        $('body').removeClass('is-page-entering is-page-exiting');
        return;
    }

    $('body').removeClass('is-page-exiting').addClass('is-page-entering');
    window.setTimeout(() => {
        $('body').removeClass('is-page-entering');
    }, 500);
}

export function navigateWithTransition(url) {
    if (!url || prefersReducedMotion || $('body').hasClass('is-page-exiting')) {
        window.location.href = url;
        return;
    }

    try {
        sessionStorage.setItem(PAGE_TRANSITION_KEY, '1');
    } catch (err) {
        /* ignore */
    }

    const $dashboardsList = $('#dashboards-list');
    if ($dashboardsList.is(':visible')) {
        $('#dashboards-toggler')
            .attr('aria-expanded', 'false')
            .attr('aria-label', 'Open dashboards');
        $dashboardsList
            .hide()
            .removeClass('dashboards-opening dashboards-closing');
    }

    markPageTransitionTargets();
    $('body').removeClass('is-page-entering').addClass('is-page-exiting');

    let navigated = false;
    const go = () => {
        if (navigated) {
            return;
        }
        navigated = true;
        window.location.href = url;
    };

    $('.page-transition-target').first().one('animationend', go);
    window.setTimeout(go, PAGE_EXIT_MS + 80);
}

function shouldInterceptNavigation(event, anchor) {
    if (event.defaultPrevented) {
        return false;
    }
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return false;
    }
    if (anchor.target && anchor.target !== '_self') {
        return false;
    }
    if (anchor.hasAttribute('download')) {
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
    // Same-page hash jumps should stay instant.
    if (url.pathname === window.location.pathname && url.hash) {
        return false;
    }

    return true;
}

$(function () {
    playPageEnter();

    $(window).on('pageshow', function (event) {
        if (event.originalEvent && event.originalEvent.persisted) {
            clearPendingTransitionFlag();
            $('body').removeClass('is-page-entering is-page-exiting');
            markPageTransitionTargets();
        }
    });

    $(document).on('click', 'a[href]', function (event) {
        const anchor = this;
        if (!shouldInterceptNavigation(event, anchor)) {
            return;
        }

        event.preventDefault();
        navigateWithTransition(anchor.href);
    });
});
