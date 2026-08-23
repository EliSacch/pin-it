/**
 * Add / edit / cancel note forms (coordinates with NoteEditor).
 */
import { closeOptionsMenu } from './disclosures.js';
import { NoteEditor } from './note-editor.js';

const $ = window.jQuery;

function focusNoteForm($form) {
    if (!$form || !$form.length) {
        return;
    }
    const title = $form.find('.note-title').get(0);
    if (!title) {
        return;
    }
    // Defer past the activating keyup/click and layout from un-hiding the form.
    // Same-turn focus from a button often leaves the input visually focused but not editable.
    window.requestAnimationFrame(function () {
        window.requestAnimationFrame(function () {
            title.focus({ preventScroll: true });
            if (typeof title.setSelectionRange === 'function') {
                const len = title.value.length;
                title.setSelectionRange(len, len);
            }
        });
    });
}

function clearNoteErrors($form) {
    if (NoteEditor && typeof NoteEditor.clearErrors === 'function') {
        NoteEditor.clearErrors($form);
        return;
    }
    $form.find('.error-msg').prop('hidden', true).empty();
    $form.find('.note-title').removeAttr('aria-invalid aria-describedby');
}

function closeAllNoteEdits() {
    const destroyPromises = [];
    $('.note-slot').each(function () {
        const $slot = $(this);
        const $form = $slot.find('.note-form');
        clearNoteErrors($form);
        if (NoteEditor && typeof NoteEditor.destroy === 'function') {
            destroyPromises.push(NoteEditor.destroy($form));
        }
        $form.trigger('reset');
        $slot.find('.note-edit').addClass('hidden-form');
        $slot.find('.note-view').removeClass('hidden-form');
    });
    return Promise.all(destroyPromises);
}

function closeAddNoteForm() {
    const $addForm = $('#addNoteForm');
    const $form = $addForm.find('.note-form');
    clearNoteErrors($form);
    let destroyPromise = Promise.resolve();
    if (NoteEditor && typeof NoteEditor.destroy === 'function') {
        destroyPromise = NoteEditor.destroy($form);
    }
    $form.trigger('reset');
    $addForm.addClass('hidden-form');
    return destroyPromise;
}

$(function () {
    $(document).on('click', '.edit-btn', function () {
        const $slot = $(this).closest('.note-slot');
        if (!$slot.length) {
            return;
        }
        Promise.all([closeAddNoteForm(), closeAllNoteEdits()]).then(function () {
            $slot.find('.note-view').addClass('hidden-form');
            $slot.find('.note-edit').removeClass('hidden-form');
            const $form = $slot.find('.note-form');
            const initPromise =
                NoteEditor && typeof NoteEditor.init === 'function'
                    ? NoteEditor.init($form)
                    : Promise.resolve();
            return Promise.resolve(initPromise).then(function () {
                focusNoteForm($form);
            });
        });
    });

    $(document).on('click', '.note-form .cancel-btn', function () {
        const $form = $(this).closest('.note-form');
        const $slot = $(this).closest('.note-slot');

        clearNoteErrors($form);
        const destroyPromise =
            NoteEditor && typeof NoteEditor.destroy === 'function'
                ? NoteEditor.destroy($form)
                : Promise.resolve();

        destroyPromise.then(function () {
            $form.trigger('reset');
            if ($slot.length) {
                $slot.find('.note-edit').addClass('hidden-form');
                $slot.find('.note-view').removeClass('hidden-form');
                $slot.find('.edit-btn').first().trigger('focus');
            } else {
                $('#addNoteForm').addClass('hidden-form');
                $('#addNoteButton').trigger('focus');
            }
        });
    });

    $('#addNoteButton').click(() => {
        closeOptionsMenu(false);
        closeAllNoteEdits().then(function () {
            const $addForm = $('#addNoteForm');
            $addForm.removeClass('hidden-form');
            const $form = $addForm.find('.note-form');
            const initPromise =
                NoteEditor && typeof NoteEditor.init === 'function'
                    ? NoteEditor.init($form)
                    : Promise.resolve();
            return Promise.resolve(initPromise).then(function () {
                focusNoteForm($form);
            });
        });
    });
});
