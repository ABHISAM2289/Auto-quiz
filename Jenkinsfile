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

        stage('Clean Up Existing Containers & Images') {
            steps {
                sh '''
                    echo "Stopping and removing containers..."
                    docker-compose down --volumes --remove-orphans || true

                    echo "Removing dangling images..."
                    docker image prune -f || true
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

                            echo "Injecting Google Cloud credentials"
                            echo "Checking if GCLOUD_JSON is available at: $GCLOUD_JSON"
                            ls -l "$GCLOUD_JSON" || { echo "GCLOUD_JSON file not found!"; exit 1; }

                            mkdir -p services/speech_to_text
                            cp "$GCLOUD_JSON" services/speech_to_text/gcloud.json
                            chmod 644 services/speech_to_text/gcloud.json

                            echo "Setting Gemini API Key"
                            echo "$GEMINI_API_KEY" > services/summarizer/gemini.key

                            echo "Building Docker images"
                            docker-compose build --no-cache

                            echo "Starting containers"
                            docker-compose up -d
                        '''
                    }
                }
            }
        }

        stage('Post Actions') {
            steps {
                echo '🚀 Deployment Complete ✅'
            }
        }
    }
}
