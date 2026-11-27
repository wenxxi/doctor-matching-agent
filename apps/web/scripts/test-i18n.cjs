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
const { translate, displayUserMessage } = require('../app/i18n.tsx');
const { recommendationFeedback } = require('../app/recommendation-types.ts');

test('temporary chat asks for details or availability changes without changing preferences', () => {
  const empty = { recommended_doctors: [], message: '目前沒有符合條件的門診。' };
  assert.deepEqual(recommendationFeedback({ ...empty, clarification_question: '哪個部位不舒服？' }), { reply: '哪個部位不舒服？', quick_replies: [] });
  const noSlots = recommendationFeedback(empty);
  assert.match(noSlots.reply, /不會自行放寬/);
  assert.ok(noSlots.quick_replies.includes('時段不限'));
  const blocked = recommendationFeedback({ ...empty, message: '院方限制本站查詢。', provider_failures: [{ http_status: 403 }] });
  assert.match(blocked.reply, /不會自動改院/);
  assert.ok(!blocked.quick_replies.includes('時段不限'));
  assert.equal(recommendationFeedback({ recommended_doctors: [{}] }), undefined);
});

test('initial preference menu labels are translated', () => {
  for (const label of ['都可以', '就診偏好（與描述一起送出）', '都可以（院方開放日期內）', '可看診時段（可複選）']) {
    assert.doesNotMatch(translate(label, 'en'), /[\u4e00-\u9fff]/);
  }
});

test('shows doctor names in generated preparation messages while preserving user text', () => {
  assert.equal(displayUserMessage('請助理安排莊雅慧醫師的門診時段。', 'en'), 'Please arrange an appointment with Dr. 莊雅慧.');
  assert.equal(displayUserMessage('請助理安排所選醫師的門診時段。', 'en'), 'Please arrange an appointment with the selected doctor.');
  assert.equal(displayUserMessage('請助理安排莊雅慧醫師的門診時段。', 'zh-TW'), '請助理安排莊雅慧醫師的門診時段。');
  assert.equal(displayUserMessage('我想請助理安排醫師，下午可以。', 'en'), '我想請助理安排醫師，下午可以。');
});

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

test('provider denial and preserved hospital preferences remain clear in English', () => {
  const message = translate('台北榮總目前限制本站查詢，暫時無法驗證該院時段；這不代表沒有名額。可保留條件稍後重試，或自行選擇改查林口長庚。 原有就診條件已保留，不會自動改院。', 'en');
  assert.match(message, /restricts this site's queries/);
  assert.match(message, /will not be changed automatically/);
  assert.doesNotMatch(message, /[\u4e00-\u9fff]/);
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
