using Microsoft.AspNetCore.Identity;

if (args.Length != 2)
{
    Console.Error.WriteLine("Expected password and encoded hash.");
    return 2;
}

var hasher = new PasswordHasher<IdentityUser>();
var result = hasher.VerifyHashedPassword(new IdentityUser(), args[1], args[0]);
if (result == PasswordVerificationResult.Failed)
{
    Console.Error.WriteLine("Microsoft PasswordHasher rejected the generated hash.");
    return 1;
}

Console.WriteLine($"Microsoft PasswordHasher accepted the generated hash: {result}");
return 0;
