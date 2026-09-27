/**
 * Loaded synchronously in <head> (not bundled, not deferred) so the pending
 * class is applied before first paint.
 */
(function () {
    try {
        if (sessionStorage.getItem('pinit-page-transition') === '1') {
            document.documentElement.classList.add('is-page-pending');
        }
    } catch (err) {
        /* ignore storage errors */
    }
})();
