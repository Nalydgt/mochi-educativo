param(
    [Parameter(Mandatory = $true)]
    [string]$PeerIP,
    [string]$Port = 'COM3'
)

$ErrorActionPreference = 'Stop'

function Test-MochiPeerIP([string]$Address) {
    if ($Address -notmatch '^(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})$') {
        return $false
    }
    $parts = @($Address.Split('.') | ForEach-Object { [int]$_ })
    return ($parts[0] -eq 100 -and $parts[1] -ge 64 -and $parts[1] -le 127 -and
            $parts[2] -le 255 -and $parts[3] -le 255)
}

if (-not (Test-MochiPeerIP $PeerIP)) {
    throw 'La IP del servidor debe ser una IPv4 de Tailscale entre 100.64.0.0 y 100.127.255.255.'
}
if ($Port -notmatch '^COM[1-9][0-9]*$') {
    throw 'Selecciona el puerto USB de Mochi, por ejemplo COM3.'
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
if (-not ('MochiVPNDialogWindow' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class MochiVPNDialogWindow {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr handle, int command);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr handle);
}
'@
}

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Configurar la VPN privada de Mochi'
$form.ClientSize = New-Object System.Drawing.Size(560, 555)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true
$form.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$form.Add_Shown({
    [MochiVPNDialogWindow]::ShowWindow($form.Handle, 5) | Out-Null
    [MochiVPNDialogWindow]::SetForegroundWindow($form.Handle) | Out-Null
})

$intro = New-Object System.Windows.Forms.Label
$intro.Text = 'La clave se envia solo por USB a Mochi. No se guarda en este PC ni se muestra en el chat. Se conserva su Wi-Fi de casa.'
$intro.Location = New-Object System.Drawing.Point(20, 15)
$intro.Size = New-Object System.Drawing.Size(520, 55)
$form.Controls.Add($intro)

$createKey = New-Object System.Windows.Forms.LinkLabel
$createKey.Text = 'Crear clave en Tailscale'
$createKey.Location = New-Object System.Drawing.Point(20, 78)
$createKey.AutoSize = $true
$createKey.Add_LinkClicked({
    try {
        Start-Process 'https://login.tailscale.com/admin/settings/keys'
    } catch {
        [System.Windows.Forms.MessageBox]::Show('Abre login.tailscale.com/admin/settings/keys en tu navegador.', 'Tailscale') | Out-Null
    }
})
$form.Controls.Add($createKey)

$instructions = New-Object System.Windows.Forms.Label
$instructions.Text = 'Crea una auth key con Reusable activado y Ephemeral desactivado. Copiala y pegala en la casilla de abajo.'
$instructions.Location = New-Object System.Drawing.Point(20, 107)
$instructions.Size = New-Object System.Drawing.Size(520, 42)
$form.Controls.Add($instructions)

$keyLabel = New-Object System.Windows.Forms.Label
$keyLabel.Text = 'Clave de Tailscale (tskey-auth-...)'
$keyLabel.Location = New-Object System.Drawing.Point(20, 155)
$keyLabel.AutoSize = $true
$form.Controls.Add($keyLabel)

$authKey = New-Object System.Windows.Forms.TextBox
$authKey.Location = New-Object System.Drawing.Point(20, 181)
$authKey.Size = New-Object System.Drawing.Size(520, 28)
$authKey.UseSystemPasswordChar = $true
$authKey.MaxLength = 127
$form.Controls.Add($authKey)

$hotspot = New-Object System.Windows.Forms.CheckBox
$hotspot.Text = 'Guardar tambien el Wi-Fi del iPhone (opcional)'
$hotspot.Location = New-Object System.Drawing.Point(20, 226)
$hotspot.Size = New-Object System.Drawing.Size(520, 28)
$form.Controls.Add($hotspot)

$ssidLabel = New-Object System.Windows.Forms.Label
$ssidLabel.Text = 'Nombre de la red del iPhone'
$ssidLabel.Location = New-Object System.Drawing.Point(20, 266)
$ssidLabel.AutoSize = $true
$form.Controls.Add($ssidLabel)

$ssid = New-Object System.Windows.Forms.TextBox
$ssid.Location = New-Object System.Drawing.Point(20, 292)
$ssid.Size = New-Object System.Drawing.Size(520, 28)
$ssid.Enabled = $false
$form.Controls.Add($ssid)

$passwordLabel = New-Object System.Windows.Forms.Label
$passwordLabel.Text = 'Contrasena de Compartir Internet'
$passwordLabel.Location = New-Object System.Drawing.Point(20, 332)
$passwordLabel.AutoSize = $true
$form.Controls.Add($passwordLabel)

$password = New-Object System.Windows.Forms.TextBox
$password.Location = New-Object System.Drawing.Point(20, 358)
$password.Size = New-Object System.Drawing.Size(520, 28)
$password.UseSystemPasswordChar = $true
$password.Enabled = $false
$form.Controls.Add($password)
$hotspot.Add_CheckedChanged({
    $ssid.Enabled = $hotspot.Checked
    $password.Enabled = $hotspot.Checked
    if (-not $hotspot.Checked) { $password.Clear() }
})

$compatibility = New-Object System.Windows.Forms.Label
$compatibility.Text = 'En el iPhone activa Compartir Internet y Maximizar la compatibilidad para usar Wi-Fi de 2,4 GHz.'
$compatibility.Location = New-Object System.Drawing.Point(20, 400)
$compatibility.Size = New-Object System.Drawing.Size(520, 44)
$form.Controls.Add($compatibility)

$destination = New-Object System.Windows.Forms.Label
$destination.Text = "Servidor privado: $PeerIP  |  USB: $Port"
$destination.Location = New-Object System.Drawing.Point(20, 453)
$destination.Size = New-Object System.Drawing.Size(520, 26)
$form.Controls.Add($destination)

$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = 'Cancelar'
$cancel.Location = New-Object System.Drawing.Point(300, 506)
$cancel.Size = New-Object System.Drawing.Size(110, 32)
$cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.Controls.Add($cancel)
$form.CancelButton = $cancel

$connect = New-Object System.Windows.Forms.Button
$connect.Text = 'Guardar en Mochi'
$connect.Location = New-Object System.Drawing.Point(420, 506)
$connect.Size = New-Object System.Drawing.Size(120, 32)
$form.Controls.Add($connect)
$form.AcceptButton = $connect

$connect.Add_Click({
    $serial = $null
    $bytes = $null
    $payload = $null
    $message = $null
    $credential = $null
    $safeFailure = 'No se pudo guardar la configuracion. Comprueba el USB y cierra cualquier monitor serie.'
    try {
        $credential = $authKey.Text.Trim()
        if ($credential.Length -lt 32 -or $credential.Length -gt 127 -or
            $credential -notmatch '^tskey-auth-[A-Za-z0-9_-]+$') {
            $safeFailure = 'Pega una auth key valida de Tailscale, con Reusable activado y Ephemeral desactivado.'
            throw 'invalid_input'
        }
        $payload = @{ auth_key = $credential; peer_ip = $PeerIP }
        if ($hotspot.Checked) {
            $name = $ssid.Text
            $nameLength = [Text.Encoding]::UTF8.GetByteCount($name)
            $passwordLength = [Text.Encoding]::UTF8.GetByteCount($password.Text)
            if ($nameLength -lt 1 -or $nameLength -gt 32 -or $name.Contains([char]0)) {
                $safeFailure = 'El nombre de la red del iPhone debe ocupar entre 1 y 32 bytes.'
                throw 'invalid_input'
            }
            if ($passwordLength -lt 8 -or $passwordLength -gt 64 -or $password.Text.Contains([char]0)) {
                $safeFailure = 'La contrasena del iPhone debe ocupar entre 8 y 64 bytes.'
                throw 'invalid_input'
            }
            $payload.hotspot_ssid = $name
            $payload.hotspot_password = $password.Text
        }
        $message = $payload | ConvertTo-Json -Compress
        $bytes = [Text.Encoding]::UTF8.GetBytes("@vpn-config $message`n")
        if ($bytes.Length -ge 1200) {
            $safeFailure = 'La configuracion es demasiado larga para el dispositivo.'
            throw 'invalid_input'
        }
        $connect.Enabled = $false
        $cancel.Enabled = $false
        $form.ControlBox = $false
        $connect.Text = 'Guardando...'
        [System.Windows.Forms.Application]::DoEvents()
        $safeFailure = 'Mochi no ha respondido. Comprueba que esta conectado por USB y cierra el monitor serie.'
        $serial = New-Object System.IO.Ports.SerialPort($Port, 115200)
        $serial.DtrEnable = $false
        $serial.RtsEnable = $false
        $serial.ReadTimeout = 250
        $serial.WriteTimeout = 3000
        $serial.Open()
        Start-Sleep -Milliseconds 300
        $serial.DiscardInBuffer()
        $serial.BaseStream.Write($bytes, 0, $bytes.Length)
        $deadline = [DateTime]::UtcNow.AddSeconds(12)
        $saved = $false
        while ([DateTime]::UtcNow -lt $deadline) {
            [System.Windows.Forms.Application]::DoEvents()
            try { $line = $serial.ReadLine() } catch [TimeoutException] { continue }
            if ($line.Contains('@mochi_vpn_config ok')) { $saved = $true; break }
            if ($line.Contains('@mochi_vpn_config invalid')) {
                $safeFailure = 'Mochi rechazo la configuracion. Espera a que termine de hablar y revisa la clave y los datos del iPhone.'
                throw 'device_rejected'
            }
        }
        if (-not $saved) { throw 'no_confirmation' }
        $authKey.Clear()
        $password.Clear()
        [System.Windows.Forms.MessageBox]::Show('Guardado. Mochi se reiniciara y conectara con tu servidor por la VPN. El Wi-Fi de casa se ha conservado.', 'Mochi') | Out-Null
        $form.Close()
    } catch {
        # Do not display exception details: no payload or credentials may leak.
        [System.Windows.Forms.MessageBox]::Show($safeFailure, 'No se pudo configurar Mochi') | Out-Null
    } finally {
        if ($null -ne $bytes) { [Array]::Clear($bytes, 0, $bytes.Length) }
        if ($null -ne $payload) { $payload.Clear() }
        $message = $null
        $credential = $null
        $authKey.Clear()
        $password.Clear()
        if ($null -ne $serial) {
            try {
                if ($serial.IsOpen) {
                    $serial.DiscardInBuffer()
                    $serial.DiscardOutBuffer()
                }
            } catch { }
            $serial.Dispose()
        }
        $connect.Enabled = $true
        $cancel.Enabled = $true
        $form.ControlBox = $true
        $connect.Text = 'Guardar en Mochi'
    }
})

try {
    [void]$form.ShowDialog()
} finally {
    $authKey.Clear()
    $password.Clear()
    $form.Dispose()
}
