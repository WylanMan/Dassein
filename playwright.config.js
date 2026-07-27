const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 15000,
  retries: 1,
  use: {
    baseURL: 'http://localhost:3000',
    viewport: { width: 1280, height: 800 },
    headless: true,
  },
  webServer: {
    command: 'python3 server.py',
    port: 3000,
    reuseExistingServer: true,
    timeout: 10000,
  },
});
