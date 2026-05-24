module.exports = {
  apps: [{
    name: "speakup-server",
    script: "./server/index.js",
    cwd: "/opt/speakup",
    env: {
      NODE_ENV: "production",
    },
  }],
};
