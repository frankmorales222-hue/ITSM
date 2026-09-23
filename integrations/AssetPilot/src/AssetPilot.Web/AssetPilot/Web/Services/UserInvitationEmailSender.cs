using System.Net;
using System.Net.Mail;
using Microsoft.Extensions.Configuration;

namespace AssetPilot.Web.Services;

public interface IUserInvitationEmailSender
{
    bool IsConfigured { get; }
    Task SendAsync(string recipient, string displayName, string invitationUrl, CancellationToken cancellationToken);
}

public sealed class UserInvitationEmailSender(IConfiguration configuration) : IUserInvitationEmailSender
{
    private string? Host => configuration["Email:Smtp:Host"];
    private string? From => configuration["Email:Smtp:FromAddress"];
    public bool IsConfigured => !string.IsNullOrWhiteSpace(Host) && !string.IsNullOrWhiteSpace(From);

    public async Task SendAsync(string recipient, string displayName, string invitationUrl, CancellationToken cancellationToken)
    {
        if (!IsConfigured) throw new InvalidOperationException("Email invitations are not configured. Add the SMTP settings before inviting a user.");
        using var message = new MailMessage(From!, recipient)
        {
            Subject = "You are invited to AssetPilot",
            IsBodyHtml = true,
            Body = $"<p>Hello {WebUtility.HtmlEncode(displayName)},</p><p>An AssetPilot account has been created for you.</p><p><a href=\"{WebUtility.HtmlEncode(invitationUrl)}\">Create your password and activate your account</a></p><p>This link is unique to your account. If you were not expecting this invitation, contact your AssetPilot administrator.</p>"
        };
        using var client = new SmtpClient(Host!, configuration.GetValue("Email:Smtp:Port", 587))
        {
            EnableSsl = configuration.GetValue("Email:Smtp:UseSsl", true)
        };
        string? username = configuration["Email:Smtp:Username"];
        if (!string.IsNullOrWhiteSpace(username)) client.Credentials = new NetworkCredential(username, configuration["Email:Smtp:Password"]);
        using var registration = cancellationToken.Register(client.SendAsyncCancel);
        await client.SendMailAsync(message, cancellationToken);
    }
}
