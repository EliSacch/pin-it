/**
 * Note text editing (Editor.js) — keep all editor/todo logic here.
 */
const $ = window.jQuery;
const editorsByHolderId = new Map();

    function getListTool() {
        return window.EditorjsList || window.List;
    }

    /**
     * Convert storage blocks → Editor.js blocks.
     * Adjacent todos become one checklist list block.
     */
    function storageBlocksToEditorBlocks(storageBlocks) {
        const editorBlocks = [];
        let todoBuffer = [];

        function flushTodos() {
            if (!todoBuffer.length) {
                return;
            }
            editorBlocks.push({
                type: 'list',
                data: {
                    style: 'checklist',
                    items: todoBuffer.map((todo) => ({
                        content: todo.text || '',
                        meta: { checked: Boolean(todo.isChecked) },
                        items: [],
                    })),
                },
            });
            todoBuffer = [];
        }

        (storageBlocks || []).forEach((block) => {
            if (!block || typeof block !== 'object') {
                return;
            }
            if (block.type === 'todo') {
                todoBuffer.push(block);
                return;
            }
            flushTodos();
            if (block.type === 'paragraph') {
                editorBlocks.push({
                    type: 'paragraph',
                    data: { text: block.text || '' },
                });
            }
        });
        flushTodos();
        return editorBlocks;
    }

    function parseJson(value, fallback) {
        if (value == null || value === '') {
            return fallback;
        }
        if (typeof value === 'object') {
            return value;
        }
        try {
            return JSON.parse(value);
        } catch (err) {
            return fallback;
        }
    }

    function resolveInitialEditorData($form) {
        const $holder = $form.find('.note-editor');
        const hiddenValue = $form.find('.note-content-json').val();
        const parsedHidden = parseJson(hiddenValue, null);

        if (parsedHidden) {
            if (Array.isArray(parsedHidden) && parsedHidden[0] && parsedHidden[0].type && parsedHidden[0].data) {
                return { blocks: parsedHidden };
            }
            if (parsedHidden.blocks) {
                return { blocks: parsedHidden.blocks };
            }
            // Storage-shaped array submitted on error after client remap — uncommon
            if (Array.isArray(parsedHidden) && parsedHidden[0] && (parsedHidden[0].type === 'paragraph' || parsedHidden[0].type === 'todo')) {
                return { blocks: storageBlocksToEditorBlocks(parsedHidden) };
            }
        }

        const storageBlocks = parseJson($holder.attr('data-storage-blocks'), []);
        return { blocks: storageBlocksToEditorBlocks(storageBlocks) };
    }

    function focusChecklistItem(editor, blockIndex, atEnd) {
        // needToFocus on insert() only marks the block focused; move the caret explicitly.
        if (editor.caret && typeof editor.caret.setToBlock === 'function') {
            editor.caret.setToBlock(blockIndex, atEnd ? 'end' : 'start');
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
            'list',
            {
                style: 'checklist',
                items: [
                    {
                        content: itemText || '',
                        meta: { checked: false },
                        items: [],
                    },
                ],
            },
            {},
            blockIndex,
            true
        );

        // Wait a frame so the list tool's contenteditable is in the DOM.
        requestAnimationFrame(function () {
            focusChecklistItem(editor, blockIndex, Boolean(itemText));
        });
    }

    function bindDashShortcut(editor, holder) {
        // Typing "--" then Space/Enter turns a paragraph into a checklist item.
        holder.addEventListener('keydown', function (event) {
            if (event.key !== ' ' && event.key !== 'Enter') {
                return;
            }
            if (event.defaultPrevented) {
                return;
            }

            const blockIndex = editor.blocks.getCurrentBlockIndex();
            const block = editor.blocks.getBlockByIndex(blockIndex);
            if (!block || block.name !== 'paragraph') {
                return;
            }

            const editable = block.holder && block.holder.querySelector('[contenteditable="true"]');
            const text = ((editable && editable.innerText) || '').replace(/\u00a0/g, ' ').replace(/\n+$/, '');

            if (event.key === ' ') {
                if (text !== '--') {
                    return;
                }
                event.preventDefault();
                replaceParagraphWithChecklistItem(editor, blockIndex, '').catch(function () {
                    /* ignore */
                });
                return;
            }

            const match = text.match(/^--\s*(.*)$/);
            if (!match) {
                return;
            }
            event.preventDefault();
            replaceParagraphWithChecklistItem(editor, blockIndex, match[1] || '').catch(function () {
                /* ignore */
            });
        });
    }

    /**
     * Editor.js List always preventDefaults Tab for nesting. With maxLevel: 1 that is a
     * no-op, so Tab never leaves the first item. Move focus between items ourselves and
     * expose checkboxes to the keyboard.
     */
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

        holder.addEventListener('keydown', function (event) {
            if (event.key !== 'Tab') {
                return;
            }
            if (!event.target || !event.target.closest) {
                return;
            }

            const listItem = event.target.closest('.cdx-list__item');
            if (!listItem) {
                return;
            }

            const listRoot = listItem.closest('.cdx-list');
            if (!listRoot) {
                return;
            }

            const focusables = Array.from(
                listRoot.querySelectorAll(
                    '.cdx-list__checkbox[tabindex="0"], .cdx-list__item-content[contenteditable="true"]'
                )
            );
            const current = event.target.closest(
                '.cdx-list__checkbox, .cdx-list__item-content'
            );
            const index = focusables.indexOf(current);
            if (index === -1) {
                return;
            }

            const nextIndex = event.shiftKey ? index - 1 : index + 1;
            // Always stop the List tool from eating Tab (it preventDefaults nesting).
            event.stopPropagation();
            event.stopImmediatePropagation();

            if (nextIndex < 0 || nextIndex >= focusables.length) {
                // At list edge: allow normal Tab to leave the list.
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
                content.id = `${holder.id || 'note-editor'}-item-${checklistLabelSeq}`;
            }
            return content.id;
        }

        function itemText(content) {
            return ((content && (content.innerText || content.textContent)) || '')
                .replace(/\u00a0/g, ' ')
                .trim();
        }

        function syncCheckboxName(el) {
            const item = el.closest('.cdx-list__item');
            const content = item && item.querySelector('.cdx-list__item-content');
            if (content && itemText(content)) {
                el.setAttribute('aria-labelledby', ensureContentId(content));
                el.removeAttribute('aria-label');
                return;
            }
            el.removeAttribute('aria-labelledby');
            el.setAttribute('aria-label', 'Checklist item');
        }

        function syncCheckboxAria(el) {
            el.setAttribute(
                'aria-checked',
                el.classList.contains('cdx-list__checkbox--checked') ? 'true' : 'false'
            );
            syncCheckboxName(el);
        }

        function enhanceCheckbox(el) {
            if (el.getAttribute('data-a11y') === '1') {
                syncCheckboxAria(el);
                return;
            }
            el.setAttribute('data-a11y', '1');
            el.setAttribute('role', 'checkbox');
            el.setAttribute('tabindex', '0');
            syncCheckboxAria(el);

            el.addEventListener('keydown', function (event) {
                if (event.key !== ' ' && event.key !== 'Enter') {
                    return;
                }
                event.preventDefault();
                event.stopPropagation();
                el.click();
                syncCheckboxAria(el);
            });
        }

        function enhanceAll() {
            holder.querySelectorAll('.cdx-list__checkbox').forEach(enhanceCheckbox);
        }

        enhanceAll();
        holder.addEventListener('input', enhanceAll);
        const observer = new MutationObserver(enhanceAll);
        observer.observe(holder, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['class'],
        });
    }

    function initNoteEditor($form) {
        if (!$form || !$form.length) {
            return Promise.resolve(null);
        }

        const $holder = $form.find('.note-editor');
        if (!$holder.length) {
            return Promise.resolve(null);
        }

        const holderId = $holder.attr('id');
        if (!holderId) {
            return Promise.resolve(null);
        }

        if (editorsByHolderId.has(holderId)) {
            return Promise.resolve(editorsByHolderId.get(holderId));
        }

        if (typeof window.EditorJS !== 'function' || typeof window.Paragraph !== 'function') {
            console.error('Editor.js tools are not loaded.');
            return Promise.resolve(null);
        }

        const ListTool = getListTool();
        if (typeof ListTool !== 'function') {
            console.error('Editor.js List tool is not loaded.');
            return Promise.resolve(null);
        }

        const holder = $holder.get(0);
        const placeholder = $holder.data('placeholder') || 'Type something...';
        const initialData = resolveInitialEditorData($form);

        const editor = new window.EditorJS({
            holder: holder,
            placeholder: placeholder,
            data: initialData,
            autofocus: false,
            minHeight: 50,
            tools: {
                paragraph: {
                    class: window.Paragraph,
                    inlineToolbar: false,
                },
                list: {
                    class: ListTool,
                    inlineToolbar: false,
                    config: {
                        defaultStyle: 'checklist',
                        maxLevel: 1,
                    },
                },
            },
        });

        editorsByHolderId.set(holderId, editor);
        return editor.isReady
            .then(function () {
                bindDashShortcut(editor, holder);
                bindChecklistAccessibility(holder);
                return editor;
            })
            .catch(function () {
                return editor;
            });
    }

    async function destroyNoteEditor($form) {
        if (!$form || !$form.length) {
            return;
        }
        const $holder = $form.find('.note-editor');
        const holderId = $holder.attr('id');
        if (!holderId || !editorsByHolderId.has(holderId)) {
            return;
        }
        const editor = editorsByHolderId.get(holderId);
        editorsByHolderId.delete(holderId);
        try {
            if (editor && typeof editor.destroy === 'function') {
                await editor.destroy();
            }
        } catch (err) {
            /* ignore destroy errors */
        }
        $holder.empty();
    }

    async function destroyAllNoteEditors() {
        const forms = $('.note-form').toArray();
        for (let i = 0; i < forms.length; i += 1) {
            await destroyNoteEditor($(forms[i]));
        }
    }

    function getEditorForForm($form) {
        const holderId = $form.find('.note-editor').attr('id');
        return holderId ? editorsByHolderId.get(holderId) : null;
    }

    function clearNoteFormErrors($form) {
        if (!$form || !$form.length) {
            return;
        }
        $form.find('.error-msg').prop('hidden', true).empty().removeAttr('tabindex');
        $form.find('.note-title').removeAttr('aria-invalid aria-describedby');
        setNoteSaveBusy($form, false);
    }

    function setNoteSaveBusy($form, isBusy) {
        const $btn = $form.find('.save-btn');
        if (!$btn.length) {
            return;
        }

        const $label = $btn.find('.btn-label');
        const $loading = $btn.find('.btn-loading');
        const idleLabel = $btn.attr('data-idle-label') || $btn.attr('aria-label') || 'Save note';
        const loadingText = $btn.data('loading-text') || 'Saving note...';

        if (!$btn.attr('data-idle-label')) {
            $btn.attr('data-idle-label', idleLabel);
        }

        if (isBusy) {
            $btn.find('.btn-loading-text').text(loadingText);
            $label.attr('hidden', true);
            $loading.removeAttr('hidden');
            $btn
                .prop('disabled', true)
                .attr('aria-busy', 'true')
                .attr('aria-label', loadingText)
                .addClass('is-loading');
            return;
        }

        $label.removeAttr('hidden');
        $loading.attr('hidden', true);
        $btn
            .prop('disabled', false)
            .removeAttr('aria-busy')
            .attr('aria-label', $btn.attr('data-idle-label') || idleLabel)
            .removeClass('is-loading');
    }

    function showNoteTitleErrors($form, messages) {
        const $errorField = $form.find('.error-msg').first();
        const $title = $form.find('.note-title').first();
        if (!$errorField.length) {
            return;
        }

        $errorField
            .prop('hidden', false)
            .html((messages || []).map(function (msg) {
                return $('<li>').text(msg)[0].outerHTML;
            }).join(''));

        const errorId = $errorField.attr('id');
        $title.attr('aria-invalid', 'true');
        if (errorId) {
            $title.attr('aria-describedby', errorId);
        }
        $title.trigger('focus');
    }

    $(document).on('submit', '.note-form', function (event) {
        const $form = $(this);
        const $errorField = $form.find('.error-msg');
        const title = $form.find('.note-title').val();
        const errors = [];

        if (title === '' || title == null) {
            errors.push('A title is required.');
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
            // Allow submit without editor (should not happen when form is open)
            return;
        }

        event.preventDefault();
        if ($form.find('.save-btn').attr('aria-busy') === 'true') {
            return;
        }

        setNoteSaveBusy($form, true);
        editor
            .save()
            .then(function (output) {
                $form.find('.note-content-json').val(JSON.stringify(output));
                $form.off('submit.noteEditorSubmit');
                // Native submit after filling hidden field
                HTMLFormElement.prototype.submit.call($form.get(0));
            })
            .catch(function () {
                setNoteSaveBusy($form, false);
                if ($errorField.length) {
                    $errorField
                        .prop('hidden', false)
                        .attr('tabindex', '-1')
                        .html('<li>Could not save note content. Please try again.</li>');
                    $errorField.trigger('focus');
                }
            });
    });

    function announceStatus(message) {
        const region = document.getElementById('a11y-status');
        if (!region) {
            return;
        }
        region.textContent = '';
        window.setTimeout(function () {
            region.textContent = message;
        }, 50);
    }

    $(document).on('change', '.note-todo-checkbox', function () {
        const $checkbox = $(this);
        const url = $checkbox.data('toggle-url');
        const csrf = $checkbox.data('csrf');
        if (!url || !csrf) {
            return;
        }

        const wasChecked = !$checkbox.prop('checked');
        $checkbox.prop('disabled', true);

        $.ajax({
            url: url,
            method: 'POST',
            data: { csrf_token: csrf },
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            dataType: 'json',
        })
            .done(function (response) {
                if (!response || !response.ok) {
                    $checkbox.prop('checked', wasChecked);
                    announceStatus('Could not update checklist item. Please try again.');
                    return;
                }
                $checkbox.prop('checked', Boolean(response.isChecked));
                $checkbox.closest('.note-todo').toggleClass('is-checked', Boolean(response.isChecked));
            })
            .fail(function () {
                $checkbox.prop('checked', wasChecked);
                announceStatus('Could not update checklist item. Please try again.');
            })
            .always(function () {
                $checkbox.prop('disabled', false);
            });
    });

    // Init editors that are already visible (e.g. validation errors)
    $(function () {
        $('.note-form').each(function () {
            const $form = $(this);
            const $wrapper = $form.closest('#addNoteForm, .note-edit');
            if ($wrapper.length && !$wrapper.hasClass('hidden-form')) {
                initNoteEditor($form);
            }
        });
    });

export const NoteEditor = {
    init: initNoteEditor,
    destroy: destroyNoteEditor,
    destroyAll: destroyAllNoteEditors,
    clearErrors: clearNoteFormErrors,
};
