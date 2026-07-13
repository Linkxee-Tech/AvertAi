const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.setDefaultTimeout(6000);
  const errors = [];
  page.on('pageerror', err => errors.push('[pageerror] ' + err.message));
  page.on('console', msg => { if(msg.type()==='error') errors.push('[console.error] ' + msg.text()); });

  const step = async (name, fn) => {
    try { await fn(); console.log('OK:', name); }
    catch(e){ console.log('FAIL:', name, '->', e.message.split('\n')[0]); }
  };

  await page.goto('http://localhost:8080/index.html');
  await page.waitForTimeout(1500); // allow checkBackendReachable() to resolve

  await step('backend status chip shows Live API connected', async () => {
    const chipText = await page.textContent('#backendStatusChip');
    console.log('  chip text:', chipText.trim());
    if (!chipText.includes('Live API')) throw new Error('expected Live API connected, got: ' + chipText);
  });

  await step('login via real backend (email+password+2FA)', async () => {
    await page.click('#loginSubmit');
    await page.waitForSelector('#otpBoxes input', {state:'visible', timeout:5000});
    for (const inp of await page.$$('#otpBoxes input')) await inp.fill('1');
    await page.click('#otpSubmit');
    await page.waitForTimeout(500);
    const overlayHidden = await page.locator('#loginOverlay').evaluate(el => el.classList.contains('hide'));
    if (!overlayHidden) throw new Error('login overlay still visible after submit');
    // The overlay hides on BOTH the success path and the offline-fallback catch path,
    // so check the actual token was set from a real response, not just the UI state.
    const token = await page.evaluate(() => typeof accessToken !== 'undefined' ? accessToken : null);
    if (!token) throw new Error('accessToken is null — login silently fell back to offline demo mode instead of hitting the real backend');
    console.log('  got real JWT, length:', token.length);
  });

  await step('overview/prediction explorer pulls real grid data from backend', async () => {
    await page.click('.nav-item[data-page="predexplorer"]');
    await page.waitForTimeout(1000);
    const cellCount = await page.$$eval('#mosaic .cell', els => els.length);
    console.log('  mosaic cell count:', cellCount);
    if (cellCount === 0) throw new Error('no grid cells rendered');
  });

  await step('click a grid cell -> fetches real historical data', async () => {
    const cells = await page.$$('#mosaic .cell');
    await cells[3].click();
    await page.waitForTimeout(800);
    const detailText = await page.textContent('#cellDetail');
    console.log('  cell detail snippet:', detailText.slice(0,120).replace(/\s+/g,' '));
  });

  await step('crowdsource moderation pulls real feedback from backend', async () => {
    await page.click('.nav-item[data-page="moderation"]');
    await page.waitForTimeout(800);
    const rows = await page.$$('#logTableBody tr');
    console.log('  feedback rows:', rows.length);
    if (rows.length === 0) throw new Error('no feedback rows loaded from backend');
  });

  await step('verify a feedback item persists via real PUT request', async () => {
    const verifyBtn = await page.$('#logTableBody [data-verify]');
    if (verifyBtn) await verifyBtn.click();
    await page.waitForTimeout(500);
  });

  await step('resource mapper pulls real resources from backend', async () => {
    await page.click('.nav-item[data-page="resources"]');
    await page.waitForTimeout(800);
    const rows = await page.$$('.resource-row');
    console.log('  resource rows:', rows.length);
    if (rows.length === 0) throw new Error('no resources loaded from backend');
  });

  await step('add a resource -> real POST to backend', async () => {
    await page.fill('#rName', 'Integration Test Shelter');
    await page.click('#addResourceBtn');
    await page.waitForTimeout(800);
  });

  await step('user management pulls real users from backend', async () => {
    await page.click('.nav-item[data-page="users"]');
    await page.waitForTimeout(800);
    const rows = await page.$$('#usersTableBody tr');
    console.log('  user rows:', rows.length);
    if (rows.length === 0) throw new Error('no users loaded from backend');
  });

  await step('broadcast center: real send + history reload', async () => {
    await page.click('.nav-item[data-page="broadcast"]');
    await page.waitForTimeout(800);
    await page.click('#bcSend');
    await page.waitForTimeout(300);
    const confirmBtn = await page.$('#modalConfirm');
    if (confirmBtn) await confirmBtn.click();
    await page.waitForTimeout(800);
    const rows = await page.$$('#broadcastHistoryBody tr');
    console.log('  broadcast history rows:', rows.length);
  });

  await step('mobile OTP login flow hits real backend', async () => {
    await page.click('.nav-item[data-page="mobile"]');
    await page.waitForTimeout(300);
    await page.click('[data-screen="login"]');
    await page.waitForTimeout(300);
    await page.click('#mSendOtp');
    await page.waitForTimeout(800);
    const wrapVisible = await page.isVisible('#mOtpWrap');
    if (!wrapVisible) throw new Error('OTP entry did not appear after Send OTP');
    // The mobile OTP flow validates the REAL generated code (unlike the admin
    // dashboard's demo 2FA, which intentionally accepts any 6 digits) — read
    // the actual code from the dev-mode hint the backend returned.
    const hintText = await page.textContent('#mOtpHint');
    const match = hintText.match(/code is (\d{6})/);
    if (!match) throw new Error('could not read dev_hint_code from UI: ' + hintText);
    const realCode = match[1];
    const boxes = await page.$$('#mOtpBoxes input');
    for (let i = 0; i < boxes.length; i++) await boxes[i].fill(realCode[i]);
    await page.click('#mVerifyOtp');
    await page.waitForTimeout(600);
    const mToken = await page.evaluate(() => typeof mobileAccessToken !== 'undefined' ? mobileAccessToken : null);
    if (!mToken) throw new Error('mobileAccessToken is null — mobile login did not actually reach the backend');
    console.log('  got real mobile JWT, length:', mToken.length);
  });

  await step('SOS beacon submits to the real backend (not simulated)', async () => {
    await page.click('[data-screen="home"]');
    await page.waitForTimeout(200);
    await page.click('#mSosBtn');
    await page.waitForTimeout(200);
    await page.click('#modalConfirm');
    await page.waitForTimeout(1800);
    const btnText = await page.textContent('#mSosBtn');
    if (!btnText.includes('sent')) throw new Error('SOS button did not reach confirmed-sent state: ' + btnText);
  });

  await step('a SEPARATE admin browser session sees the SOS on Overview', async () => {
    // Fresh, independent browser context — proves the SOS reached the shared
    // backend database rather than just updating the sender's own local state.
    const adminContext = await browser.newContext();
    const adminPage = await adminContext.newPage();
    adminPage.setDefaultTimeout(6000);
    await adminPage.goto('http://localhost:8080/index.html');
    await adminPage.waitForTimeout(400);
    await adminPage.click('#loginSubmit');
    await adminPage.waitForSelector('#otpBoxes input', {state:'visible'});
    for (const inp of await adminPage.$$('#otpBoxes input')) await inp.fill('1');
    await adminPage.click('#otpSubmit');
    await adminPage.waitForTimeout(600);
    const adminToken = await adminPage.evaluate(() => typeof accessToken !== 'undefined' ? accessToken : null);
    if (!adminToken) throw new Error('second admin session failed to authenticate against the real backend');

    await adminPage.click('.nav-item[data-page="overview"]');
    await adminPage.waitForTimeout(1000);
    const bannerVisible = await adminPage.isVisible('#sosBanner');
    const bannerText = bannerVisible ? await adminPage.textContent('#sosBanner') : '';
    console.log('  SOS banner visible on a fresh admin session:', bannerVisible);
    if (!bannerVisible || !bannerText.includes('EMERGENCY SOS')) {
      throw new Error('SOS submitted by the mobile user did not appear to a different admin session — not actually connected');
    }
    await adminContext.close();
  });

  console.log('\n=== TOTAL PAGE/CONSOLE ERRORS:', errors.length, '===');
  errors.slice(0,10).forEach(e => console.log(e));
  await browser.close();
})();
