using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Win32.SafeHandles;

namespace FMFaceRefresh;

/// <summary>Windows paths and local file URLs compared on directory boundaries.</summary>
public static class GraphicsPaths
{
    public static string? Canonical(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return null;
        var path = value.Trim();
        if (!Regex.IsMatch(path, @"^[a-zA-Z]:[\\/]") && Uri.TryCreate(path, UriKind.Absolute, out var uri) && uri.IsFile)
            path = (uri.Host.Length > 0 && uri.Host != "localhost" ? "//" + uri.Host : "") + Uri.UnescapeDataString(uri.AbsolutePath);
        else if (path.Contains("://")) return null;
        path = path.Replace('\\', '/');
        if (path.StartsWith("//?/UNC/", StringComparison.OrdinalIgnoreCase)) path = "//" + path[8..];
        else if (path.StartsWith("//?/", StringComparison.Ordinal)) path = path[4..];
        if (Regex.IsMatch(path, @"^/[a-zA-Z]:/")) path = path[1..];
        string root, rest;
        if (Regex.IsMatch(path, @"^[a-zA-Z]:/")) { root = path[..2]; rest = path[3..]; }
        else if (path.StartsWith("//"))
        {
            var components = path[2..].Split('/', StringSplitOptions.RemoveEmptyEntries);
            if (components.Length < 2) return null;
            root = "//" + components[0] + "/" + components[1]; rest = string.Join("/", components.Skip(2));
        }
        else return null;
        var parts = new List<string>();
        foreach (var part in rest.Split('/', StringSplitOptions.RemoveEmptyEntries))
        {
            if (part == ".") continue;
            if (part == "..") { if (parts.Count > 0) parts.RemoveAt(parts.Count - 1); }
            else parts.Add(part);
        }
        return root + "/" + string.Join("/", parts);
    }

    public static bool Contains(string? root, string? folder)
    {
        var parent = Canonical(root)?.TrimEnd('/');
        var child = Canonical(folder)?.TrimEnd('/');
        return parent is not null && child is not null && (string.Equals(parent, child, StringComparison.OrdinalIgnoreCase)
            || child.StartsWith(parent + "/", StringComparison.OrdinalIgnoreCase));
    }

    public static string Kind(string? path) => path is null ? "empty" : path.Contains("://") ? "uri"
        : Canonical(path) is not null ? "absolute_windows" : "relative_or_virtual";

    public static string? Physical(string? path)
    {
        var normal = Canonical(path);
        // Only resolve local metadata handles; do not initiate network filesystem connections.
        if (!OperatingSystem.IsWindows() || normal is null || !Regex.IsMatch(normal, @"^[a-zA-Z]:/")) return null;
        using var handle = CreateFileW(normal, 0, 7, IntPtr.Zero, 3, 0x02000000, IntPtr.Zero);
        if (handle.IsInvalid) return null;
        var text = new StringBuilder(1024);
        var length = GetFinalPathNameByHandleW(handle, text, (uint)text.Capacity, 0);
        if (length == 0 || length > 32768) return null;
        if (length >= text.Capacity)
        {
            text = new StringBuilder((int)length + 1);
            if (GetFinalPathNameByHandleW(handle, text, (uint)text.Capacity, 0) == 0) return null;
        }
        return Canonical(text.ToString());
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    private static extern SafeFileHandle CreateFileW(string name, uint access, uint sharing, IntPtr security, uint disposition, uint flags, IntPtr template);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    private static extern uint GetFinalPathNameByHandleW(SafeFileHandle file, StringBuilder path, uint length, uint flags);
}

/// <summary>Use an existing native root, or explicitly register only the selected pack once.</summary>
public sealed class GraphicsRegistration
{
    private readonly HashSet<string> added = new(StringComparer.OrdinalIgnoreCase);
    public bool Ensure(string pack, Func<string, bool> covered, Action<string> register)
    {
        var key = GraphicsPaths.Canonical(pack) ?? throw new ArgumentException("Expected an absolute Windows pack path");
        if (covered(pack) || added.Contains(key)) return false;
        register(pack); // Add only after a successful registration call; failed calls are not remembered.
        added.Add(key);
        return true;
    }
}
