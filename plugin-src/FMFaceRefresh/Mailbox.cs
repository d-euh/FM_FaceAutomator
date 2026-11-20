namespace FMFaceRefresh;

/// <summary>Retry only local delivery. Never retry a native rescan to resend its reply.</summary>
public sealed class Mailbox
{
    private Action? pendingReply;
    public bool HasReply => pendingReply is not null;
    public long Failures { get; private set; }
    public string LastError { get; private set; } = "";
    public string? LastFailureUtc { get; private set; }

    public bool Try(string phase, Action action)
    {
        try { action(); return true; }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            Failures++;
            LastError = phase + ":" + exception.GetType().Name;
            LastFailureUtc = DateTimeOffset.UtcNow.ToString("O");
            return false;
        }
    }

    public void QueueReply(Action send)
    {
        if (pendingReply is not null) throw new InvalidOperationException("A reply is already awaiting delivery");
        pendingReply = send;
    }

    public void FlushReply()
    {
        if (pendingReply is not null && Try("write_response", pendingReply)) pendingReply = null;
    }
}
