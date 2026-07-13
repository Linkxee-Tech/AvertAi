const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();

  // Mobile user session — standalone app
  const mobilePage = await (await browser.newContext()).newPage();
  mobilePage.setDefaultTimeout(6000);
  await mobilePage.goto('http://localhost:8080/mobile/index.html');
  await mobilePage.waitForTimeout(600);
  // skip onboarding
  await mobilePage.click('#mOnboardNext'); await mobilePage.waitForTimeout(100);
  await mobilePage.click('#mOnboardNext'); await mobilePage.waitForTimeout(100);
  await mobilePage.click('#mOnboardNext'); await mobilePage.waitForTimeout(200);
  await mobilePage.click('#modalConfirm'); await mobilePage.waitForTimeout(200);
  // login as a distinct phone number
  await mobilePage.fill('#mPhoneInput', '+254788800001');
  await mobilePage.click('#mSendOtp');
  await mobilePage.waitForTimeout(700);
  const hint = await mobilePage.textContent('#mOtpHint');
  const code = hint.match(/code is (\d{6})/)[1];
  const boxes = await mobilePage.$$('#mOtpBoxes input');
  for (let i=0;i<boxes.length;i++) await boxes[i].fill(code[i]);
  await mobilePage.click('#mVerifyOtp');
  await mobilePage.waitForTimeout(800);

  // submit a flood report from the mobile app
  await mobilePage.click('#bottomTabBar [data-screen="report"]');
  await mobilePage.waitForTimeout(200);
  await mobilePage.click('[data-report="Flood"]');
  await mobilePage.fill('#m-report textarea', 'Water rising fast near the market, 1km east');
  await mobilePage.click('#mSubmitReport');
  await mobilePage.waitForTimeout(500);
  const refText = await mobilePage.textContent('#modalBody');
  const ref = refText.match(/RPT-\d{4}-\d+/)[0];
  console.log('Mobile user submitted report, reference:', ref);
  await mobilePage.click('#modalConfirm');

  // Admin session — completely separate app (admin dashboard)
  const adminPage = await (await browser.newContext()).newPage();
  adminPage.setDefaultTimeout(6000);
  await adminPage.goto('http://localhost:8080/index.html');
  await adminPage.waitForTimeout(600);
  await adminPage.click('#loginSubmit');
  await adminPage.waitForSelector('#otpBoxes input', {state:'visible'});
  for (const inp of await adminPage.$$('#otpBoxes input')) await inp.fill('1');
  await adminPage.click('#otpSubmit');
  await adminPage.waitForTimeout(600);

  await adminPage.click('.nav-item[data-page="moderation"]');
  await adminPage.waitForTimeout(1000);
  const tableText = await adminPage.textContent('#logTableBody');
  const found = tableText.includes('Water rising fast near the market');
  console.log('Admin moderation table contains the mobile report text:', found);
  if (!found) { console.log('FULL TABLE TEXT:', tableText); }

  await browser.close();
  process.exit(found ? 0 : 1);
})();
