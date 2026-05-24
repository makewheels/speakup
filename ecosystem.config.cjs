module.exports = {
  apps: [{
    name: "speakup-server",
    script: "main.py",
    cwd: "/opt/speakup/server",
    interpreter: "uv",
    interpreter_args: "run python",
    env: {
      APP_ENV: "production",
    },
  }],
};
