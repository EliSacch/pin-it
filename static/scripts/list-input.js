/**
 * Chip-based list input (see templates/forms/inputs/listInput.html).
 * Values typed or pasted into the entry field are split on commas/whitespace
 * and turned into removable chips, each carrying a hidden input with the
 * list's field name so the form submits one repeated field per item.
 */
const $ = window.jQuery;

const SEPARATOR = /[\s,]+/;

const emailProbe = document.createElement('input');
emailProbe.type = 'email';

const itemTypes = {
    text: {
        normalize: (value) => value,
        isValid: () => true,
        invalidMessage: 'Remove invalid entries.',
    },
    email: {
        normalize: (value) => value.toLowerCase(),
        isValid: (value) => {
            emailProbe.value = value;
            return emailProbe.checkValidity();
        },
        invalidMessage: 'Remove or fix invalid email addresses.',
    },
};

export function registerListItemType(name, config) {
    itemTypes[name] = { ...itemTypes.text, ...config };
}

function itemTypeFor($root) {
    return itemTypes[$root.data('item-type')] || itemTypes.text;
}

function splitTokens(text) {
    return (text || '').split(SEPARATOR).map((token) => token.trim()).filter(Boolean);
}

function entryFor($root) {
    return $root.find('.list-input-entry').first();
}

function chipValue($chip) {
    return $chip.find('input[type="hidden"]').val();
}

function currentValues($root) {
    return $root.find('.list-input-chip').map(function () {
        return chipValue($(this));
    }).get();
}

function announce($root, message) {
    $root.find('.list-input-status').text(message);
}

function markChipValidity($root, $chip) {
    const isValid = itemTypeFor($root).isValid(chipValue($chip));
    $chip.toggleClass('is-invalid', !isValid);
    $chip.find('.list-input-chip-invalid').remove();
    if (!isValid) {
        $chip.find('.list-input-chip-label')
            .append('<span class="visually-hidden list-input-chip-invalid"> (invalid)</span>');
    }
}

function syncState($root) {
    const $chips = $root.find('.list-input-chip');
    $root.find('.list-input-chips').prop('hidden', !$chips.length);

    const $entry = entryFor($root);
    const itemLabel = $root.data('item-label') || 'item';
    let message = '';
    if ($chips.filter('.is-invalid').length) {
        message = itemTypeFor($root).invalidMessage;
    } else if ($entry.attr('aria-required') === 'true' && !$chips.length) {
        message = `Add at least one ${itemLabel}.`;
    }
    $entry.get(0).setCustomValidity(message);
}

function buildChip($root, value) {
    const template = $root.find('.list-input-chip-template').get(0);
    const $chip = $(template.content.firstElementChild.cloneNode(true));
    const itemLabel = $root.data('item-label') || 'item';

    $chip.find('.list-input-chip-label').text(value);
    $chip.find('.list-input-chip-remove').attr('aria-label', `Remove ${itemLabel} ${value}`);
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
        $root.find('.list-input-chips').append(buildChip($root, value));
        added.push(value);
    });

    syncState($root);
    if (added.length) {
        announce($root, `Added ${added.join(', ')}.`);
    }
}

function removeChip($chip, { focusNext = true } = {}) {
    const $root = $chip.closest('[data-list-input]');
    const value = chipValue($chip);
    const $sibling = $chip.next('.list-input-chip').length
        ? $chip.next('.list-input-chip')
        : $chip.prev('.list-input-chip');

    $chip.remove();
    syncState($root);
    announce($root, `Removed ${value}.`);

    if (focusNext) {
        const $target = $sibling.length
            ? $sibling.find('.list-input-chip-remove')
            : entryFor($root);
        $target.trigger('focus');
    }
}

function commitEntry($root) {
    const $entry = entryFor($root);
    const text = $entry.val();
    if (!text || !text.trim()) {
        $entry.val('');
        return;
    }
    $entry.val('');
    addItems($root, text);
}

function setItems($root, values) {
    $root.find('.list-input-chip').remove();
    const $chips = $root.find('.list-input-chips');
    values.forEach((value) => $chips.append(buildChip($root, value)));
    syncState($root);
}

export function commitListInputs($form) {
    $form.find('[data-list-input]').each(function () {
        commitEntry($(this));
    });
}

function initListInput($root) {
    if ($root.data('list-input-ready')) {
        return;
    }
    $root.data('list-input-ready', true);
    $root.data('initial-values', currentValues($root));
    $root.find('.list-input-chip').each(function () {
        markChipValidity($root, $(this));
    });
    syncState($root);
}

$(function () {
    $('[data-list-input]').each(function () {
        initListInput($(this));
    });

    $(document).on('input', '.list-input-entry', function () {
        const $entry = $(this);
        const value = $entry.val();
        if (!SEPARATOR.test(value)) {
            return;
        }
        const $root = $entry.closest('[data-list-input]');
        const endsWithSeparator = /[\s,]$/.test(value);
        const tokens = splitTokens(value);
        const pending = endsWithSeparator ? '' : tokens.pop() || '';
        $entry.val(pending);
        addItems($root, tokens.join(','));
    });

    $(document).on('keydown', '.list-input-entry', function (event) {
        const $entry = $(this);
        const $root = $entry.closest('[data-list-input]');

        if (event.key === 'Enter' && $entry.val().trim()) {
            event.preventDefault();
            commitEntry($root);
            return;
        }

        if (event.key === 'Backspace' && !$entry.val()) {
            const $last = $root.find('.list-input-chip').last();
            if ($last.length) {
                event.preventDefault();
                removeChip($last, { focusNext: false });
            }
        }
    });

    $(document).on('focusout', '.list-input-entry', function () {
        commitEntry($(this).closest('[data-list-input]'));
    });

    $(document).on('click', '.list-input-chip-remove', function () {
        removeChip($(this).closest('.list-input-chip'));
    });

    $(document).on('reset', 'form', function () {
        $(this).find('[data-list-input]').each(function () {
            const $root = $(this);
            setItems($root, $root.data('initial-values') || []);
            announce($root, '');
        });
    });
});
