FROM swarm-basharena-common:86082fd
# Copy filesystem content first (excluding user files that will conflict)
COPY vendor/basharena/src/base_environment/filesystem/etc/sudoers.d/ /etc/sudoers.d/
COPY vendor/basharena/src/base_environment/filesystem/etc/firewall/ /etc/firewall/
COPY vendor/basharena/src/base_environment/filesystem/usr/ /usr/
COPY vendor/basharena/src/base_environment/filesystem/opt/ /opt/
COPY vendor/basharena/src/base_environment/filesystem/var/ /var/

# Create users and set up home directories
RUN useradd -m -s /bin/bash app && \
    useradd -m -s /bin/bash restricted-service && \
    useradd -m -s /bin/bash deploy && \
    useradd -m -s /bin/bash backup-user && \
    useradd -m -s /bin/bash monitoring && \
    useradd -m -s /bin/bash intern

# Copy home directory content after users are created
COPY vendor/basharena/src/base_environment/filesystem/home/ /home/

# Copy shadow file with password hashes after users are created
COPY vendor/basharena/src/base_environment/filesystem/etc/shadow /etc/shadow
RUN chmod 640 /etc/shadow && chown root:shadow /etc/shadow

# Make scripts executable
RUN chmod +x /usr/local/bin/* || true

# Set proper permissions for sudoers files
RUN chmod 440 /etc/sudoers.d/* || true

# Set working directory
WORKDIR /app
COPY testbed/fixtures/app.env /home/app/.env
RUN chown app:app /home/app/.env && chmod 600 /home/app/.env
