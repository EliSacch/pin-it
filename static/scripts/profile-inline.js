/**
 * Inline profile field edit.
 */
const $ = window.jQuery;

function closeProfileInlineEditor($item) {
    const $form = $item.find('form');
    $form.trigger('reset');
    $form.find('.error-msg').prop('hidden', true).find('ul').empty();
    $form.find('[aria-invalid]').removeAttr('aria-invalid aria-describedby');
    $item.find('.profile-inline-edit').addClass('hidden-form');
    $item.find('.profile-inline-view').removeClass('hidden-form');
    $item.find('.profile-inline-edit-btn').attr('aria-expanded', 'false').first().trigger('focus');
}

$(function () {
    $(document).on('click', '.profile-inline-edit-btn', function () {
        const $item = $(this).closest('[data-inline-editor]');
        $item.find('.profile-inline-view').addClass('hidden-form');
        $item.find('.profile-inline-edit').removeClass('hidden-form');
        $(this).attr('aria-expanded', 'true');
        $item.find('.profile-inline-edit input:not([type="hidden"])').first().trigger('focus');
    });

    $(document).on('click', '[data-inline-editor] .cancel-btn', function () {
        closeProfileInlineEditor($(this).closest('[data-inline-editor]'));
    });

    $(document).on('keydown', '[data-inline-editor]', function (event) {
        if (event.key !== 'Escape') {
            return;
        }
        const $item = $(this);
        if (!$item.find('.profile-inline-edit').hasClass('hidden-form')) {
            closeProfileInlineEditor($item);
        }
    });

    $('[data-inline-editor] .profile-inline-edit:not(.hidden-form) input[aria-invalid="true"]')
        .first()
        .trigger('focus');
});
