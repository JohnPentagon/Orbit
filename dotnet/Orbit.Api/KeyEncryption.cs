using System.Xml.Linq;
using Microsoft.AspNetCore.DataProtection.XmlEncryption;

namespace Orbit.Api;

public sealed class KeyEncryption(Cipher cipher) : IXmlEncryptor
{
    public EncryptedXmlInfo Encrypt(XElement plaintextElement) =>
        new(
            new XElement(
                "orbitEncryptedKey",
                cipher.Protect(plaintextElement.ToString(SaveOptions.DisableFormatting))
            ),
            typeof(KeyDecryption)
        );
}

public sealed class KeyDecryption(IServiceProvider services) : IXmlDecryptor
{
    public XElement Decrypt(XElement encryptedElement) =>
        XElement.Parse(services.GetRequiredService<Cipher>().Unprotect(encryptedElement.Value));
}
