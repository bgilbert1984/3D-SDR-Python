const { test, expect } = require('@jest/globals');
const { renderElement, renderLeaf } = require('../../frontend/frontend-signal-visualization');

test('renderElement should return a paragraph for default type', () => {
    const props = { element: { type: 'paragraph' }, attributes: {}, children: 'Test' };
    const result = renderElement(props);
    expect(result.type).toBe('p');
    expect(result.props.children).toBe('Test');
});

test('renderLeaf should apply bold styling', () => {
    const props = { leaf: { bold: true }, attributes: {}, children: 'Bold Text' };
    const result = renderLeaf(props);
    expect(result.type).toBe('span');
    expect(result.props.children.type).toBe('strong');
    expect(result.props.children.props.children).toBe('Bold Text');
});