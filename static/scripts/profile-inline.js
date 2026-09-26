/**
 * Inline profile field edit.
 */
const $ = window.jQuery;
const editButtonSelector = '.profile-inline-edit-btn, [data-inline-editor-trigger]';
const editPanelSelector = '.profile-inline-edit, [data-inline-editor-panel]';
const viewSelector = '.profile-inline-view, [data-inline-editor-view]';

function closeProfileInlineEditor($item) {
    const $form = $item.find('form');
    $form.trigger('reset');
    $form.find('.error-msg').prop('hidden', true).find('ul').empty();
    $form.find('[aria-invalid]').removeAttr('aria-invalid aria-describedby');
    $item.find(editPanelSelector).addClass('hidden-form');
    $item.find(viewSelector).removeClass('hidden-form');
    $item.find(editButtonSelector).attr('aria-expanded', 'false').first().trigger('focus');
}

$(function () {
    $(document).on('click', editButtonSelector, function () {
        const $item = $(this).closest('[data-inline-editor]');
        $item.find(viewSelector).addClass('hidden-form');
        $item.find(editPanelSelector).removeClass('hidden-form');
        $(this).attr('aria-expanded', 'true');
        $item.find(editPanelSelector)
            .find('input:not([type="hidden"])')
            .first()
            .trigger('focus');
    });

    $(document).on('click', '[data-inline-editor] .cancel-btn', function () {
        closeProfileInlineEditor($(this).closest('[data-inline-editor]'));
    });

    $(document).on('keydown', '[data-inline-editor]', function (event) {
        if (event.key !== 'Escape') {
            return;
        }
        const $item = $(this);
        if (!$item.find(editPanelSelector).hasClass('hidden-form')) {
            closeProfileInlineEditor($item);
        }
    });

    $('[data-inline-editor]')
        .find(editPanelSelector)
        .filter(':not(.hidden-form)')
        .find('input[aria-invalid="true"]')
        .first()
        .trigger('focus');
});
