const vscode = require('vscode');

function activate(context) {
    let disposable = vscode.commands.registerCommand('atp-vscode-poc.helloWorld', function () {
        vscode.window.showInformationMessage('ATP VS Code POC Activated!');
    });
    context.subscriptions.push(disposable);
}

function deactivate() {}

module.exports = {
    activate,
    deactivate
};
