pipeline {
    agent any

    environment {
        REPO_URL = 'https://github.com/ABHISAM2289/Auto-quiz.git'
    }

    stages {

        stage('Checkout SCM') {
            steps {
                git branch: 'main', url: "${env.REPO_URL}"
            }
        }

        stage('Clean Up Docker Environment') {
            steps {
                sh '''
                    echo "🧹 Stopping and removing all containers..."
                    docker-compose down --volumes --remove-orphans || true

                    echo "🧹 Removing all unused containers, networks, images, and volumes..."
                    docker system prune -a -f || true

                    echo "🧹 Removing dangling volumes..."
                    docker volume prune -f || true

                    echo "✅ Clean up complete."
                '''
            }
        }

        stage('Build and Deploy') {
            steps {
                withCredentials([
                    file(credentialsId: 'gcloud-service-account', variable: 'GCLOUD_JSON'),
                    string(credentialsId: 'GEMINI_API_SUMMARIZER', variable: 'GEMINI_API_KEY')
                ]) {
                    dir('Auto-quiz') {
                        sh '''
                            set -e

                            echo "🔐 Injecting Google Cloud credentials"
                            echo "Checking if GCLOUD_JSON is available at: $GCLOUD_JSON"
                            ls -l "$GCLOUD_JSON" || { echo "GCLOUD_JSON file not found!"; exit 1; }

                            mkdir -p services/speech_to_text
                            cp "$GCLOUD_JSON" services/speech_to_text/gcloud.json
                            chmod 644 services/speech_to_text/gcloud.json

                            echo "🔐 Writing Gemini API key to file"
                            echo "$GEMINI_API_KEY" > services/summarizer/gemini.key

                            echo "🐳 Building Docker images (no cache)"
                            DOCKER_BUILDKIT=0 docker-compose build --no-cache

                            echo "🚀 Starting containers"
                            docker-compose up -d --force-recreate
                        '''
                    }
                }
            }
        }

        stage('Post Actions') {
            steps {
                echo '✅ Deployment Completed Successfully 🚀'
            }
        }
    }
}
