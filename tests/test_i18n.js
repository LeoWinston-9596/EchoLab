/* Shared translation behaviour: fallback, saved preference and language changes. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '..', 'i18n.js'), 'utf8');
function setup(saved, browserLanguage, blockedStorage = false) {
  const listeners = {};
  const node = {dataset: {i18n: '素材库'}, textContent: ''};
  const context = {
    navigator: {language: browserLanguage},
    localStorage: {
      getItem() {if (blockedStorage) throw new Error('blocked'); return saved;},
      setItem(key, value) {if (blockedStorage) throw new Error('blocked'); saved = value;},
    },
    document: {
      documentElement: {},
      querySelectorAll(selector) {return selector === '[data-i18n]' ? [node] : [];},
      addEventListener(event, fn) {listeners[event] = fn;},
    },
    window: {addEventListener() {}, dispatchEvent() {}},
    CustomEvent: class {},
  };
  vm.runInNewContext(source, context);
  listeners.DOMContentLoaded();
  return {api: context.window.EchoI18n, node, context};
}
const english = setup(null, 'en-AU');
assert.equal(english.node.textContent, 'Library');
assert.equal(english.api.t('Original learning content'), 'Original learning content');
english.api.setLanguage('zh-CN');
assert.equal(english.node.textContent, '素材库');
english.api.setLanguage('en');
assert.equal(english.node.textContent, 'Library');
english.api.setLanguage('unsupported');
assert.equal(english.api.language, 'en');
assert.equal(setup('en', 'zh-CN').node.textContent, 'Library');
assert.equal(setup(null, 'zh-CN', true).node.textContent, '素材库');
console.log('UI language fallback, persistence and round-trip checks passed.');
