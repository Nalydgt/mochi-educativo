param(
    [string]$SettingsPath,
    [string]$Port = 'COM3'
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class MochiDialogWindow {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr handle, int command);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr handle);
}
'@
$settings = Get-Content -LiteralPath $SettingsPath -Raw | ConvertFrom-Json
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Conectar Mochi al Wi-Fi de casa'
$form.ClientSize = New-Object System.Drawing.Size(440, 245)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true
$form.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$form.Add_Shown({
    [MochiDialogWindow]::ShowWindow($form.Handle, 5) | Out-Null
    [MochiDialogWindow]::SetForegroundWindow($form.Handle) | Out-Null
})
$intro = New-Object System.Windows.Forms.Label
$intro.Text = 'Introduce tu red de 2,4 GHz. La clave se envia solo por USB a Mochi y no se guarda en este PC.'
$intro.Location = New-Object System.Drawing.Point(20, 15)
$intro.Size = New-Object System.Drawing.Size(400, 48)
$form.Controls.Add($intro)
$ssidLabel = New-Object System.Windows.Forms.Label
$ssidLabel.Text = 'Nombre de la red Wi-Fi'
$ssidLabel.Location = New-Object System.Drawing.Point(20, 70)
$ssidLabel.AutoSize = $true
$form.Controls.Add($ssidLabel)
$ssid = New-Object System.Windows.Forms.TextBox
$ssid.Location = New-Object System.Drawing.Point(20, 96)
$ssid.Size = New-Object System.Drawing.Size(400, 28)
$form.Controls.Add($ssid)
$passwordLabel = New-Object System.Windows.Forms.Label
$passwordLabel.Text = 'Contrasena'
$passwordLabel.Location = New-Object System.Drawing.Point(20, 132)
$passwordLabel.AutoSize = $true
$form.Controls.Add($passwordLabel)
$password = New-Object System.Windows.Forms.TextBox
$password.UseSystemPasswordChar = $true
$password.Location = New-Object System.Drawing.Point(20, 158)
$password.Size = New-Object System.Drawing.Size(400, 28)
$form.Controls.Add($password)
$connect = New-Object System.Windows.Forms.Button
$connect.Text = 'Conectar'
$connect.Location = New-Object System.Drawing.Point(300, 201)
$connect.Size = New-Object System.Drawing.Size(120, 30)
$form.Controls.Add($connect)
$form.AcceptButton = $connect
$connect.Add_Click({
    $serial = $null
    try {
        $name = $ssid.Text.Trim()
        if (-not $name -or [Text.Encoding]::UTF8.GetByteCount($name) -gt 32) {
            throw 'Escribe un nombre de red de entre 1 y 32 bytes.'
        }
        $length = [Text.Encoding]::UTF8.GetByteCount($password.Text)
        if ($length -gt 64 -or ($length -gt 0 -and $length -lt 8)) {
            throw 'La clave Wi-Fi debe tener entre 8 y 64 bytes.'
        }
        $connect.Enabled = $false
        $connect.Text = 'Conectando...'
        $serial = New-Object System.IO.Ports.SerialPort($Port, 115200)
        $serial.DtrEnable = $false
        $serial.RtsEnable = $false
        $serial.ReadTimeout = 250
        $serial.WriteTimeout = 3000
        $serial.Open()
        Start-Sleep -Milliseconds 400
        $serial.DiscardInBuffer()
        $message = @{ssid=$name; password=$password.Text; server_url=$settings.server_url; token=$settings.token} | ConvertTo-Json -Compress
        $bytes = [Text.Encoding]::UTF8.GetBytes("@config $message`n")
        $serial.BaseStream.Write($bytes, 0, $bytes.Length)
        $deadline = [DateTime]::UtcNow.AddSeconds(12)
        $saved = $false
        while ([DateTime]::UtcNow -lt $deadline) {
            try { $line = $serial.ReadLine() } catch [TimeoutException] { continue }
            if ($line.Contains('@mochi_config ok')) { $saved = $true; break }
            if ($line.Contains('@mochi_config invalid')) { throw 'Mochi rechazo la configuracion. Revisa la red y su clave.' }
        }
        if (-not $saved) { throw 'Mochi no ha respondido por USB. Cierra el monitor serie y vuelve a intentarlo.' }
        $password.Clear()
        $message = $null
        [Array]::Clear($bytes, 0, $bytes.Length)
        [System.Windows.Forms.MessageBox]::Show('Configuracion guardada. Mochi se reiniciara y conectara con el servidor de casa.', 'Mochi') | Out-Null
        $form.Close()
    } catch {
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'No se pudo conectar Mochi') | Out-Null
    } finally {
        if ($null -ne $serial) { $serial.Dispose() }
        $connect.Enabled = $true
        $connect.Text = 'Conectar'
    }
})
[void]$form.ShowDialog()
$password.Clear()
$form.Dispose()
