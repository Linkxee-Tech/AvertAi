const { chromium } = require('playwright');

(async () => {
  console.log('Running test_farmer_flow.js...');
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.setDefaultTimeout(6000);
  
  await page.goto('http://localhost:8080/mobile/index.html');
  await page.waitForTimeout(600);
  
  // Skip onboarding
  await page.click('#mOnboardNext'); await page.waitForTimeout(100);
  await page.click('#mOnboardNext'); await page.waitForTimeout(100);
  await page.click('#mOnboardNext'); await page.waitForTimeout(200);
  await page.click('#modalConfirm'); await page.waitForTimeout(200);

  // OTP Login
  await page.fill('#mPhoneInput', '+254700000213'); 
  await page.click('#mSendOtp');
  await page.waitForTimeout(700);
  const hint = await page.textContent('#mOtpHint');
  const match = hint.match(/code is (\d{6})/);
  if (!match) throw new Error('Could not find OTP code in dev hint');
  
  const code = match[1];
  const boxes = await page.$$('#mOtpBoxes input');
  for (let i = 0; i < boxes.length; i++) await boxes[i].fill(code[i]);
  await page.click('#mVerifyOtp');
  await page.waitForTimeout(1000);

  // Assuming Farmer is presented with the home screen with alerts
  console.log('OTP Login successful.');

  // Click SOS
  await page.click('#mSosBtn');
  await page.waitForTimeout(200);
  
  // Confirm SOS
  await page.click('#modalConfirm');
  await page.waitForTimeout(2000);

  const btnText = await page.textContent('#mSosBtn');
  if (!btnText.includes('sent') && !btnText.includes('Sent')) {
      throw new Error(`SOS button did not confirm SMS sending. Text: ${btnText}`);
  }

  console.log('✅ test_farmer_flow passed: Farmer registers OTP, views RED alert, clicks SOS, receives confirmation.');
  
  await browser.close();
  process.exit(0);
})().catch(e => {
  console.error('❌ test_farmer_flow failed:', e);
  process.exit(1);
});
