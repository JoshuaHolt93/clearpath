export function PasswordRequirements() {
  return (
    <div className="password-requirements" aria-label="Password requirements">
      <div className="password-requirements-title">Password requirements</div>
      <ul>
        <li>At least 12 characters</li>
        <li>Uppercase and lowercase letters</li>
        <li>At least one number and one symbol</li>
        <li>Does not include your email address</li>
      </ul>
    </div>
  );
}
