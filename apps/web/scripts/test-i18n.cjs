const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const ts = require('typescript');

// Load the pure translator without introducing a separate test framework.
for (const extension of ['.ts', '.tsx']) {
  require.extensions[extension] = (module, filename) => {
    const result = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 },
    });
    module._compile(result.outputText, filename);
  };
}
const { translate } = require('../app/i18n.tsx');

test('translates a prefixed assistant question as a complete English message', () => {
  const text = translate('已更新這次條件。上午、下午或夜診，哪些時段可以？也可以回答時段不限。', 'en');
  assert.match(text, /preferences have been updated/);
  assert.match(text, /morning, afternoon, or evening/);
  assert.doesNotMatch(text, /[\u4e00-\u9fff]/);
});

test('preserves verified counts and incomplete-lookup notices in compound messages', () => {
  const text = translate('目前確認 2 位相關醫師有符合條件的掛號時段；其餘未確認可掛號的醫師已排除。 部分院方時段無法確認，已排除未確認的醫師；可稍後重新查詢。', 'en');
  assert.match(text, /2 relevant doctor/);
  assert.match(text, /could not be verified/);
  assert.doesNotMatch(text, /[\u4e00-\u9fff]/);
});

test('retains doctor names and dates while translating status text', () => {
  assert.match(translate('查詢黃毓智的四週門診時段。', 'en'), /黃毓智/);
  assert.equal(translate('已確認2099-10-19 下午的院方患者資料頁可開啟。', 'en'), 'Verified the hospital patient form for 2099-10-19, Afternoon.');
});

test('translates hospital eligibility and handoff without claiming a booking', () => {
  const question = translate('已更新這次條件。榮總需要確認是否曾在該院看診，才能查詢正確資格的時段。這次是全院初診或複診？若不確定，可先改找林口長庚。', 'en');
  assert.match(question, /first or returning visit/);
  assert.doesNotMatch(question, /[\u4e00-\u9fff]/);
  assert.match(translate('請在院方頁面選取上列日期與時段。點擊連結不代表掛號成功，名額以院方送出時為準。', 'en'), /does not book/);
});

test('leaves unknown source content and canonical values intact', () => {
  for (const value of ['CGMH_LINKOU_TEST', 'returning', 'TEST123', 'constructor', '__proto__', '患者自行填寫的個案名稱。']) {
    assert.equal(translate(value, 'en'), value);
    assert.equal(translate(value, 'zh-TW'), value);
  }
  assert.equal(translate(undefined, 'en'), '');
});

test('uses Chinese labels in Chinese mode and distinguishes eligibility restrictions', () => {
  assert.equal(translate('週', 'en'), '');
  assert.equal(translate('Recommended Doctors', 'zh-TW'), '推薦醫師');
  assert.match(translate('初診可掛（從未在本院看診）', 'en'), /First hospital visit only/);
  assert.match(translate('科初診可掛（半年內未看過該科）', 'en'), /First departmental visit/);
  assert.match(translate('一般掛號（資格以院方確認為準）', 'en'), /General registration/);
});
